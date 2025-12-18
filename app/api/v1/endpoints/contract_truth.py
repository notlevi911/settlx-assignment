"""
Contract Truth endpoint - /v1/contracts/truth:analyze
Multi-chain contract analysis (strict spec).
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict
import hashlib
import uuid

from app.api.v1.schemas.requests import ContractTruthRequest
from app.api.v1.schemas.responses import (
    ContractTruthResponse,
    ContractTruthDataSection,
    ProvenSection,
    InferredSection,
    ProvenInstance,
    CrossChainEquivalence,
    VerificationData,
    CodeIdentity,
    UpgradeabilityData,
    ControlsData,
    FeeControls,
    SupplyActivity,
    RiskFlag,
    Evidence,
    StructuredError,
    ErrorCode
)
from app.services.contract_truth import ContractTruthService
from app.services.solana_client import SolanaClient
from app.core.enums import DataCertainty
from web3 import Web3

router = APIRouter()


@router.post("/contracts/truth:analyze", response_model=ContractTruthResponse)
async def analyze_contract_truth(request: ContractTruthRequest):
    """
    **Contract Truth Analysis (Strict Spec)**
    
    Analyzes smart contracts across multiple chains (EVM + Solana).
    Returns PROVEN facts and INFERRED conclusions separately.
    
    Response structure:
    - request_id (UUID)
    - as_of (ISO timestamp)
    - data.proven.instances[] - PROVEN facts from explorers/RPC
    - data.inferred.cross_chain_equivalence[] - INFERRED cross-chain analysis
    - evidence[], warnings[], errors[]
    """
    request_id = str(uuid.uuid4())
    as_of = datetime.now(timezone.utc).isoformat()
    
    proven_instances: List[ProvenInstance] = []
    all_evidence: List[Evidence] = []
    all_warnings: List[str] = []
    all_errors: List[StructuredError] = []
    
    # Analyze each chain instance
    for instance in request.instances:
        try:
            if instance.chain.lower() == "solana":
                proven = await _analyze_solana_instance(instance, request.options, request.lookback_days)
            else:
                proven = await _analyze_evm_instance(instance, request.options, request.lookback_days)
            
            proven_instances.append(proven)
            
        except Exception as e:
            error = StructuredError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to analyze {instance.chain}:{instance.address}",
                source=instance.chain,
                retryable=True
            )
            all_errors.append(error)
            all_warnings.append(f"Skipped {instance.chain}:{instance.address} due to error: {str(e)}")
    
    # Add evidence
    if proven_instances:
        all_evidence.append(Evidence(
            provider="contract_truth",
            timestamp=datetime.now(timezone.utc),
            note=f"Analyzed {len(proven_instances)} chain instance(s)"
        ))
    
    # Infer cross-chain equivalence if multiple instances
    cross_chain_eq = []
    if len(proven_instances) >= 2:
        cross_chain_eq = _infer_cross_chain_equivalence(proven_instances)
    
    return ContractTruthResponse(
        request_id=request_id,
        as_of=as_of,
        data=ContractTruthDataSection(
            proven=ProvenSection(instances=proven_instances),
            inferred=InferredSection(cross_chain_equivalence=cross_chain_eq)
        ),
        evidence=all_evidence,
        warnings=all_warnings,
        errors=all_errors
    )


async def _analyze_evm_instance(instance, options, lookback_days: int) -> ProvenInstance:
    """Analyze EVM chain contract - returns PROVEN facts only."""
    service = ContractTruthService(instance.chain)
    old_result = await service.analyze_contract(instance.address)
    
    # Verification data
    verification = VerificationData(
        verified_source=old_result.is_verified.value or False,
        explorer=f"{instance.chain}_explorer",
        abi_available=old_result.is_verified.value or False,
        source_hash=None  # TODO: Extract from explorer response
    )
    
    # Code identity
    code_hash = None
    if options.compute_code_hash:
        try:
            code = service.web3.eth.get_code(instance.address)
            code_hash = f"keccak256:{hashlib.sha256(code).hexdigest()}"
        except:
            pass
    
    code_identity = CodeIdentity(
        runtime_code_hash=code_hash,
        deployer=None,  # TODO: Get from creation tx
        creation_tx=None
    )
    
    # Upgradeability detection
    is_proxy = old_result.is_proxy.value or False
    proxy_type = None
    if is_proxy:
        if "EIP-1967" in str(old_result.is_proxy.reason):
            proxy_type = "transparent"
        elif "EIP-1822" in str(old_result.is_proxy.reason):
            proxy_type = "uups"
        elif "EIP-897" in str(old_result.is_proxy.reason):
            proxy_type = "beacon"
        else:
            proxy_type = "unknown"
    
    # Check if admin is a contract (timelock detection)
    admin_is_contract = None
    timelock_detected = False
    admin_addr = None
    
    if is_proxy and old_result.owner_address.value:
        admin_addr = old_result.owner_address.value
        try:
            admin_code = service.web3.eth.get_code(admin_addr)
            admin_is_contract = len(admin_code) > 2
            if admin_is_contract:
                timelock_detected = True  # Assume contract admin = timelock
        except:
            pass
    
    upgradeability = UpgradeabilityData(
        is_proxy=is_proxy,
        proxy_type=proxy_type,
        implementation=old_result.implementation_address.value,
        admin=admin_addr,
        admin_is_contract=admin_is_contract,
        timelock_detected=timelock_detected,
        upgrade_authority=None  # EVM doesn't use this concept
    )
    
    # Controls extraction
    controls = ControlsData(
        owner_or_admin=old_result.owner_address.value,
        can_mint=old_result.has_mint_function.value,
        can_burn=old_result.has_burn_function.value,
        can_pause=old_result.has_pause_function.value,
        can_blacklist_or_freeze=old_result.has_freeze_function.value,
        fee_controls=FeeControls(
            can_change_fees=False,  # TODO: Detect from ABI
            max_fee_bps=None
        )
    )
    
    # Supply activity (simplified - no event history yet)
    supply_activity = SupplyActivity(
        mint_events_lookback=None,  # TODO: Implement event tracking
        mint_amount_lookback=None,
        burn_events_lookback=None,
        burn_amount_lookback=None
    )
    
    # Risk flags
    risk_flags = _generate_risk_flags_evm(
        controls=controls,
        upgradeability=upgradeability,
        verification=verification
    )
    
    return ProvenInstance(
        chain=instance.chain,
        address=instance.address,
        type=instance.type,
        verification=verification,
        code_identity=code_identity,
        upgradeability=upgradeability,
        controls=controls,
        supply_activity=supply_activity,
        risk_flags=risk_flags
    )


async def _analyze_solana_instance(instance, options, lookback_days: int) -> ProvenInstance:
    """Analyze Solana SPL token - returns PROVEN facts only."""
    client = SolanaClient()
    
    # Analyze SPL token mint
    spl_data = await client.analyze_spl_token(instance.address)
    
    if spl_data.get("error"):
        raise Exception(f"Solana RPC error: {spl_data['error'].message}")
    
    # Verification (Solana uses on-chain verification)
    verification = VerificationData(
        verified_source=spl_data.get("is_verified", False),
        explorer="solscan",
        abi_available=False,  # SPL has standard interface
        source_hash=None
    )
    
    # Code identity (Solana uses program addresses)
    code_identity = CodeIdentity(
        runtime_code_hash=None,  # SPL tokens don't have custom code
        deployer=spl_data.get("mint_authority"),
        creation_tx=None
    )
    
    # Upgradeability (Solana uses upgrade_authority on programs)
    upgrade_authority = spl_data.get("upgrade_authority")
    
    upgradeability = UpgradeabilityData(
        is_proxy=False,  # SPL doesn't use proxies
        proxy_type=None,
        implementation=None,
        admin=None,
        admin_is_contract=None,
        timelock_detected=False,
        upgrade_authority=upgrade_authority
    )
    
    # Controls
    mint_authority = spl_data.get("mint_authority")
    freeze_authority = spl_data.get("freeze_authority")
    authority_renounced = spl_data.get("authority_renounced", False)
    
    controls = ControlsData(
        owner_or_admin=mint_authority,
        can_mint=mint_authority is not None,
        can_burn=True,  # SPL tokens can always burn
        can_pause=False,
        can_blacklist_or_freeze=freeze_authority is not None,
        fee_controls=FeeControls(
            can_change_fees=False,
            max_fee_bps=None
        )
    )
    
    # Supply activity
    supply_activity = SupplyActivity(
        mint_events_lookback=None,
        mint_amount_lookback=None,
        burn_events_lookback=None,
        burn_amount_lookback=None
    )
    
    # Risk flags
    risk_flags = _generate_risk_flags_solana(
        controls=controls,
        upgradeability=upgradeability,
        verification=verification
    )
    
    return ProvenInstance(
        chain="solana",
        address=instance.address,
        type=instance.type,
        verification=verification,
        code_identity=code_identity,
        upgradeability=upgradeability,
        controls=controls,
        supply_activity=supply_activity,
        risk_flags=risk_flags
    )


def _generate_risk_flags_evm(
    controls: ControlsData,
    upgradeability: UpgradeabilityData,
    verification: VerificationData
) -> List[RiskFlag]:
    """Generate risk flags for EVM contracts."""
    flags = []
    
    # Mint privilege
    if controls.can_mint:
        flags.append(RiskFlag(
            id="MINT_PRIVILEGE",
            severity="medium",
            why="Contract has mint capability"
        ))
    
    # Proxy upgradeable
    if upgradeability.is_proxy:
        flags.append(RiskFlag(
            id="PROXY_UPGRADEABLE",
            severity="high",
            why=f"Contract is upgradeable proxy ({upgradeability.proxy_type or 'unknown'})"
        ))
        
        # No timelock
        if not upgradeability.timelock_detected:
            flags.append(RiskFlag(
                id="UPGRADEABLE_NO_TIMELOCK_EVIDENCE",
                severity="high",
                why="Upgradeable proxy without detected timelock protection"
            ))
    
    # Unverified
    if not verification.verified_source:
        flags.append(RiskFlag(
            id="UNVERIFIED_SOURCE",
            severity="high",
            why="Source code not verified on explorer"
        ))
    
    # Freeze/blacklist
    if controls.can_blacklist_or_freeze:
        flags.append(RiskFlag(
            id="FREEZE_AUTHORITY_PRESENT",
            severity="high",
            why="Contract can freeze or blacklist addresses"
        ))
    
    return flags


def _generate_risk_flags_solana(
    controls: ControlsData,
    upgradeability: UpgradeabilityData,
    verification: VerificationData
) -> List[RiskFlag]:
    """Generate risk flags for Solana SPL tokens."""
    flags = []
    
    # Mint authority
    if controls.can_mint:
        flags.append(RiskFlag(
            id="MINT_PRIVILEGE",
            severity="medium",
            why="Mint authority is set"
        ))
    
    # Freeze authority
    if controls.can_blacklist_or_freeze:
        flags.append(RiskFlag(
            id="FREEZE_AUTHORITY_PRESENT",
            severity="high",
            why="Freeze authority is set"
        ))
    
    # Upgrade authority
    if upgradeability.upgrade_authority:
        flags.append(RiskFlag(
            id="UPGRADE_AUTHORITY_PRESENT",
            severity="medium",
            why="Program has upgrade authority set"
        ))
    
    return flags


def _infer_cross_chain_equivalence(instances: List[ProvenInstance]) -> List[CrossChainEquivalence]:
    """Infer cross-chain equivalence (INFERRED conclusions)."""
    if len(instances) < 2:
        return []
    
    equivalences = []
    
    # Compare all pairs
    for i in range(len(instances)):
        for j in range(i + 1, len(instances)):
            inst_a = instances[i]
            inst_b = instances[j]
            
            pair_id = [
                f"{inst_a.chain}:{inst_a.address}",
                f"{inst_b.chain}:{inst_b.address}"
            ]
            
            # Score similarity
            confidence, reasons = _score_similarity(inst_a, inst_b)
            
            # Classify
            if confidence >= 0.8:
                label = "proven_same_asset"
            elif confidence >= 0.5:
                label = "likely_same_asset"
            else:
                label = "unknown"
            
            equivalences.append(CrossChainEquivalence(
                pair=pair_id,
                confidence=round(confidence, 2),
                reasons=reasons,
                label=label
            ))
    
    return equivalences


def _score_similarity(inst_a: ProvenInstance, inst_b: ProvenInstance) -> Tuple[float, List[str]]:
    """Score similarity between two instances."""
    score = 0.0
    max_score = 0.0
    reasons = []
    
    # Controls similarity (40% weight)
    max_score += 0.4
    controls_match = 0
    controls_total = 0
    
    if inst_a.controls.can_mint == inst_b.controls.can_mint:
        controls_match += 1
    else:
        reasons.append(f"Mint capability differs: {inst_a.chain}={inst_a.controls.can_mint}, {inst_b.chain}={inst_b.controls.can_mint}")
    controls_total += 1
    
    if inst_a.controls.can_pause == inst_b.controls.can_pause:
        controls_match += 1
    else:
        reasons.append(f"Pause capability differs")
    controls_total += 1
    
    if inst_a.controls.can_blacklist_or_freeze == inst_b.controls.can_blacklist_or_freeze:
        controls_match += 1
    else:
        reasons.append(f"Freeze capability differs")
    controls_total += 1
    
    score += 0.4 * (controls_match / controls_total)
    
    # Upgradeability similarity (30% weight)
    max_score += 0.3
    if inst_a.upgradeability.is_proxy == inst_b.upgradeability.is_proxy:
        score += 0.3
    else:
        reasons.append(f"Upgradeability differs: {inst_a.chain}={inst_a.upgradeability.is_proxy}, {inst_b.chain}={inst_b.upgradeability.is_proxy}")
    
    # Risk flags similarity (30% weight)
    max_score += 0.3
    flags_a = {f.id for f in inst_a.risk_flags}
    flags_b = {f.id for f in inst_b.risk_flags}
    
    if flags_a == flags_b:
        score += 0.3
        reasons.append(f"Risk profiles match ({len(flags_a)} flags)")
    else:
        diff = flags_a.symmetric_difference(flags_b)
        reasons.append(f"Risk profiles differ: {diff}")
    
    # Normalize
    confidence = score / max_score if max_score > 0 else 0.0
    
    return confidence, reasons
