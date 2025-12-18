"""
Contract Truth endpoint - /v1/contracts/truth:analyze
Multi-chain contract analysis with Solana support.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List
import hashlib

from app.api.v1.schemas.requests import ContractTruthRequest
from app.api.v1.schemas.responses import (
    ContractTruthResponse,
    ChainAnalysis,
    ControlExtraction,
    ProxyType,
    Evidence,
    StructuredError,
    ErrorCode
)
from app.services.contract_truth import ContractTruthService
from app.services.solana_client import SolanaClient
from app.services.contract_analyzer import ContractAnalyzer
from app.core.enums import DataCertainty
from web3 import Web3

router = APIRouter()


@router.post("/contracts/truth:analyze", response_model=ContractTruthResponse)
async def analyze_contract_truth(request: ContractTruthRequest):
    """
    **Contract Truth Analysis**
    
    Analyzes smart contracts across multiple chains (EVM + Solana).
    Returns verification status, proxy detection, admin controls, and supply tracking.
    
    Supports:
    - EVM chains: ethereum, bsc, polygon, arbitrum, avalanche
    - Solana: SPL token analysis
    
    All data classified as PROVEN, INFERRED, or UNKNOWN with evidence tracking.
    """
    analyses: List[ChainAnalysis] = []
    all_errors: List[StructuredError] = []
    all_warnings: List[str] = []
    
    # Analyze each chain instance
    for instance in request.instances:
        try:
            if instance.chain.lower() == "solana":
                analysis = await _analyze_solana(instance, request.options, request.lookback_days)
            else:
                analysis = await _analyze_evm(instance, request.options, request.lookback_days)
            
            analyses.append(analysis)
            all_errors.extend(analysis.evidence)
            
        except Exception as e:
            # Partial failure - add error but continue
            error = StructuredError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to analyze {instance.chain}:{instance.address}: {str(e)}",
                source=instance.chain,
                retryable=True
            )
            all_errors.append(error)
            
            # Add placeholder analysis with error
            analyses.append(ChainAnalysis(
                chain=instance.chain,
                address=instance.address,
                type=instance.type,
                controls=ControlExtraction(),
                evidence=[Evidence(
                    provider=instance.chain,
                    timestamp=datetime.now(timezone.utc),
                    note=f"Analysis failed: {str(e)}"
                )],
                unknown_fields=["all"]
            ))
    
    # Cross-chain consistency check
    cross_chain_consistent, cross_chain_notes = _check_cross_chain_consistency(analyses)
    
    # Calculate overall risk score
    overall_risk = _calculate_overall_risk(analyses)
    critical_flags = _extract_critical_flags(analyses)
    
    return ContractTruthResponse(
        token={"symbol": request.token.symbol, "name": request.token.name or ""},
        timestamp=datetime.now(timezone.utc),
        analyses=analyses,
        cross_chain_consistent=cross_chain_consistent,
        cross_chain_notes=cross_chain_notes,
        overall_risk_score=overall_risk,
        critical_flags=critical_flags,
        errors=[e for e in all_errors if isinstance(e, StructuredError)],
        warnings=all_warnings
    )


async def _analyze_evm(instance, options, lookback_days: int) -> ChainAnalysis:
    """Analyze EVM chain contract."""
    try:
        service = ContractTruthService(instance.chain)
        old_result = await service.analyze_contract(instance.address)
        
        # Convert old format to new format
        controls = ControlExtraction(
            has_mint=old_result.has_mint_function.value if old_result.has_mint_function.value is not None else None,
            has_burn=old_result.has_burn_function.value if old_result.has_burn_function.value is not None else None,
            has_pause=old_result.has_pause_function.value if old_result.has_pause_function.value is not None else None,
            has_freeze=old_result.has_freeze_function.value if old_result.has_freeze_function.value is not None else None,
            owner_address=old_result.owner_address.value,
            ownership_renounced=old_result.ownership_renounced.value
        )
        
        # Determine proxy type
        proxy_type = ProxyType.NOT_PROXY
        if old_result.is_proxy.value:
            # Enhanced proxy type detection
            if "EIP-1967" in str(old_result.is_proxy.reason):
                proxy_type = ProxyType.EIP1967_TRANSPARENT  # Would need upgrade to detect UUPS
            elif "EIP-1822" in str(old_result.is_proxy.reason):
                proxy_type = ProxyType.EIP1822_UUPS
            elif "EIP-897" in str(old_result.is_proxy.reason):
                proxy_type = ProxyType.EIP897
            else:
                proxy_type = ProxyType.CUSTOM
        
        # Compute code hash if requested
        code_hash = None
        if options.compute_code_hash:
            try:
                code = service.web3.eth.get_code(instance.address)
                code_hash = hashlib.sha256(code).hexdigest()
            except:
                pass
        
        # Classify fields
        proven_fields = []
        inferred_fields = []
        unknown_fields = []
        
        if old_result.is_verified.certainty == DataCertainty.PROVEN:
            proven_fields.extend(["is_verified", "controls"])
        if old_result.is_proxy.certainty == DataCertainty.PROVEN:
            proven_fields.append("proxy_type")
        if old_result.total_supply.certainty == DataCertainty.UNKNOWN:
            unknown_fields.append("current_supply")
        if old_result.supply_change_24h.certainty == DataCertainty.UNKNOWN:
            unknown_fields.extend(["supply_change_24h_pct", "supply_change_7d_pct"])
        
        return ChainAnalysis(
            chain=instance.chain,
            address=instance.address,
            type=instance.type,
            is_verified=old_result.is_verified.value,
            verification_source=old_result.is_verified.source,
            proxy_type=proxy_type,
            implementation_address=old_result.implementation_address.value,
            is_upgradeable=old_result.is_upgradeable.value,
            controls=controls,
            code_hash=code_hash,
            compiler_version=old_result.compiler_version.value,
            current_supply=old_result.total_supply.value,
            supply_change_24h_pct=None,  # TODO: Implement historical tracking
            supply_change_7d_pct=None,
            evidence=[
                Evidence(
                    provider=f"{instance.chain}_explorer",
                    timestamp=old_result.timestamp,
                    note="EVM contract analysis via block explorer + RPC"
                )
            ],
            proven_fields=proven_fields,
            inferred_fields=inferred_fields,
            unknown_fields=unknown_fields
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EVM analysis failed: {str(e)}")


async def _analyze_solana(instance, options, lookback_days: int) -> ChainAnalysis:
    """Analyze Solana SPL token."""
    client = SolanaClient()
    
    # Analyze SPL token mint
    spl_data = await client.analyze_spl_token(instance.address)
    
    if spl_data.get("error"):
        return ChainAnalysis(
            chain="solana",
            address=instance.address,
            type=instance.type,
            is_verified=False,
            controls=ControlExtraction(),
            evidence=[
                Evidence(
                    provider="solana_rpc",
                    timestamp=datetime.now(timezone.utc),
                    note=f"Error: {spl_data['error'].message}"
                )
            ],
            unknown_fields=["all"]
        )
    
    # Get supply
    supply, supply_error = await client.get_token_supply(instance.address)
    
    controls = ControlExtraction(
        has_mint=spl_data.get("mint_authority") is not None,
        has_freeze=spl_data.get("freeze_authority") is not None,
        owner_address=spl_data.get("mint_authority"),
        ownership_renounced=spl_data.get("authority_renounced", False)
    )
    
    proven_fields = ["is_verified", "controls", "current_supply"] if spl_data.get("is_verified") else []
    unknown_fields = ["proxy_type", "code_hash", "supply_change_24h_pct", "supply_change_7d_pct"]
    
    return ChainAnalysis(
        chain="solana",
        address=instance.address,
        type=instance.type,
        is_verified=spl_data.get("is_verified", False),
        verification_source="solana_rpc",
        proxy_type=ProxyType.NOT_PROXY,  # Solana doesn't use proxies same way
        implementation_address=None,
        is_upgradeable=None,  # Would need to check program owner
        controls=controls,
        code_hash=None,
        compiler_version=None,
        current_supply=supply,
        supply_change_24h_pct=None,
        supply_change_7d_pct=None,
        evidence=[
            Evidence(
                provider="solana_rpc",
                timestamp=datetime.now(timezone.utc),
                note="SPL token mint analysis"
            )
        ],
        proven_fields=proven_fields,
        inferred_fields=[],
        unknown_fields=unknown_fields
    )


def _check_cross_chain_consistency(analyses: List[ChainAnalysis]) -> tuple[bool, List[str]]:
    """Check if controls are consistent across chains."""
    if len(analyses) <= 1:
        return True, []
    
    notes = []
    
    # Check mint authority consistency
    mint_values = [a.controls.has_mint for a in analyses if a.controls.has_mint is not None]
    if len(set(mint_values)) > 1:
        notes.append("⚠️ Inconsistent mint authority across chains")
    
    # Check ownership renounced
    renounced_values = [a.controls.ownership_renounced for a in analyses if a.controls.ownership_renounced is not None]
    if len(set(renounced_values)) > 1:
        notes.append("⚠️ Ownership renounced on some chains but not others")
    
    # Check upgradeability
    upgradeable_values = [a.is_upgradeable for a in analyses if a.is_upgradeable is not None]
    if len(set(upgradeable_values)) > 1:
        notes.append("⚠️ Upgradeability differs across chains")
    
    return len(notes) == 0, notes


def _calculate_overall_risk(analyses: List[ChainAnalysis]) -> int:
    """Calculate overall risk score from all chain analyses."""
    if not analyses:
        return 100
    
    total_risk = 0
    for analysis in analyses:
        risk = 0
        
        # Unverified contract
        if analysis.is_verified is False:
            risk += 30
        
        # Upgradeable proxy
        if analysis.is_upgradeable:
            risk += 25
        
        # Mint authority present
        if analysis.controls.has_mint:
            risk += 20
        
        # Pause/Freeze
        if analysis.controls.has_pause:
            risk += 15
        if analysis.controls.has_freeze:
            risk += 20
        
        # Owner not renounced
        if analysis.controls.ownership_renounced is False:
            risk += 10
        
        total_risk += min(risk, 100)
    
    # Average across chains
    return min(total_risk // len(analyses), 100)


def _extract_critical_flags(analyses: List[ChainAnalysis]) -> List[str]:
    """Extract critical risk flags."""
    flags = []
    
    for analysis in analyses:
        prefix = f"[{analysis.chain}]"
        
        if analysis.is_verified is False:
            flags.append(f"{prefix} UNVERIFIED_CONTRACT")
        
        if analysis.is_upgradeable:
            flags.append(f"{prefix} UPGRADEABLE_PROXY")
        
        if analysis.controls.has_mint:
            flags.append(f"{prefix} MINTABLE")
        
        if analysis.controls.has_pause:
            flags.append(f"{prefix} PAUSABLE")
        
        if analysis.controls.has_freeze:
            flags.append(f"{prefix} FREEZABLE")
    
    return list(set(flags))  # Dedupe
