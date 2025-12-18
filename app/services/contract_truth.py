"""
Contract Truth Service - Main orchestrator.
Combines blockchain analysis, explorer data, and risk detection.
"""
from datetime import datetime
from typing import Dict, Optional
from web3 import Web3
from app.core.models import ContractTruthResponse, CertainData, RiskFlagDetail
from app.core.enums import DataCertainty, RiskFlag
from app.core.config import settings
from app.services.contract_analyzer import ContractAnalyzer
from app.services.explorer_client import ExplorerClient


class ContractTruthService:
    """
    Determines if a token contract is safe to integrate.
    Classifies all data as PROVEN, INFERRED, or UNKNOWN.
    """
    
    def __init__(self, chain: str):
        self.chain = chain.lower()
        rpc_url = settings.get_rpc_url(self.chain)
        
        if not rpc_url:
            raise ValueError(f"No RPC URL configured for chain: {chain}")
        
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        self.analyzer = ContractAnalyzer(self.web3)
        self.explorer = ExplorerClient(chain)
    
    async def analyze_contract(self, address: str) -> ContractTruthResponse:
        """
        Full contract analysis pipeline.
        Every field is classified as PROVEN, INFERRED, or UNKNOWN.
        """
        risk_flags = []
        
        # Step 1: Fetch source code and verification status
        source_data = await self.explorer.get_contract_source(address)
        
        is_verified = CertainData(
            value=source_data.get("verified", False),
            certainty=DataCertainty.PROVEN,
            source=f"{self.chain} block explorer API",
            reason=None
        )
        
        source_code = source_data.get("source_code")
        source_code_available = CertainData(
            value=source_code is not None,
            certainty=DataCertainty.PROVEN,
            source=f"{self.chain} block explorer API",
            reason=None
        )
        
        compiler_version = CertainData(
            value=source_data.get("compiler_version"),
            certainty=DataCertainty.PROVEN if source_data.get("verified") else DataCertainty.UNKNOWN,
            source=f"{self.chain} block explorer API" if source_data.get("verified") else None,
            reason="Contract not verified" if not source_data.get("verified") else None
        )
        
        # Risk flag: Unverified contract
        if not is_verified.value:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.UNVERIFIED_CONTRACT,
                evidence=f"Contract source code not verified on {self.chain} explorer",
                severity=8,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 2: Proxy detection
        is_proxy_val, impl_address, proxy_evidence = self.analyzer.detect_proxy(address)
        
        is_proxy = CertainData(
            value=is_proxy_val,
            certainty=DataCertainty.PROVEN,
            source="On-chain storage slots (EIP-1967/1822/897)",
            reason=proxy_evidence
        )
        
        implementation_address = CertainData(
            value=impl_address,
            certainty=DataCertainty.PROVEN if is_proxy_val else DataCertainty.UNKNOWN,
            source="On-chain storage slots",
            reason="Not a proxy contract" if not is_proxy_val else None
        )
        
        # Step 3: Upgradeability check
        is_upgradeable_val, upgrade_evidence = self.analyzer.check_upgradeability(address, is_proxy_val)
        
        is_upgradeable = CertainData(
            value=is_upgradeable_val,
            certainty=DataCertainty.PROVEN if is_proxy_val else DataCertainty.INFERRED,
            source="On-chain function signature detection",
            reason=upgrade_evidence
        )
        
        # Risk flag: Upgradeable proxy
        if is_upgradeable_val:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.UPGRADEABLE_PROXY,
                evidence=upgrade_evidence,
                severity=7,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 4: Admin function detection
        admin_functions = self.analyzer.detect_admin_functions(source_code)
        
        has_mint_val, mint_evidence = admin_functions.get("mint", (False, "Cannot determine"))
        has_mint_function = CertainData(
            value=has_mint_val,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="Source code analysis" if source_code else None,
            reason=mint_evidence if source_code else "Source code not available"
        )
        
        if has_mint_val:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.MINTABLE,
                evidence=mint_evidence,
                severity=6,
                certainty=DataCertainty.PROVEN
            ))
        
        has_burn_val, burn_evidence = admin_functions.get("burn", (False, "Cannot determine"))
        has_burn_function = CertainData(
            value=has_burn_val,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="Source code analysis" if source_code else None,
            reason=burn_evidence if source_code else "Source code not available"
        )
        
        if has_burn_val:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.BURNABLE,
                evidence=burn_evidence,
                severity=3,
                certainty=DataCertainty.PROVEN
            ))
        
        has_pause_val, pause_evidence = admin_functions.get("pause", (False, "Cannot determine"))
        has_pause_function = CertainData(
            value=has_pause_val,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="Source code analysis" if source_code else None,
            reason=pause_evidence if source_code else "Source code not available"
        )
        
        if has_pause_val:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.PAUSABLE,
                evidence=pause_evidence,
                severity=7,
                certainty=DataCertainty.PROVEN
            ))
        
        has_freeze_val, freeze_evidence = admin_functions.get("freeze", (False, "Cannot determine"))
        has_freeze_function = CertainData(
            value=has_freeze_val,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="Source code analysis" if source_code else None,
            reason=freeze_evidence if source_code else "Source code not available"
        )
        
        if has_freeze_val:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.FREEZABLE,
                evidence=freeze_evidence,
                severity=8,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 5: Ownership detection
        owner_addr, is_renounced, ownership_evidence = self.analyzer.detect_ownership(source_code, address)
        
        owner_address = CertainData(
            value=owner_addr,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="On-chain owner() call" if source_code else None,
            reason=ownership_evidence
        )
        
        ownership_renounced = CertainData(
            value=is_renounced,
            certainty=DataCertainty.PROVEN if source_code else DataCertainty.UNKNOWN,
            source="On-chain owner() call" if source_code else None,
            reason=ownership_evidence
        )
        
        if not is_renounced and owner_addr:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.OWNERSHIP_NOT_RENOUNCED,
                evidence=f"Active owner: {owner_addr}",
                severity=5,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 6: Supply tracking
        total_supply_val = await self._get_total_supply(address)
        total_supply = CertainData(
            value=total_supply_val,
            certainty=DataCertainty.PROVEN if total_supply_val is not None else DataCertainty.UNKNOWN,
            source="On-chain totalSupply() call" if total_supply_val is not None else None,
            reason="totalSupply() call failed" if total_supply_val is None else None
        )
        
        # Supply change tracking (INFERRED - requires historical data)
        supply_change_24h = CertainData(
            value=None,
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="Historical supply tracking not implemented (requires indexed events)"
        )
        
        supply_change_7d = CertainData(
            value=None,
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="Historical supply tracking not implemented (requires indexed events)"
        )
        
        # Step 7: Cross-chain detection (INFERRED)
        cross_chain_addresses = CertainData(
            value={},
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="Cross-chain token mapping requires external registry (not implemented)"
        )
        
        cross_chain_confidence = CertainData(
            value=None,
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="Cross-chain detection not implemented"
        )
        
        # Step 8: Calculate risk score
        contract_risk_score = self._calculate_risk_score(risk_flags)
        
        return ContractTruthResponse(
            chain=self.chain,
            address=address,
            timestamp=datetime.utcnow(),
            is_verified=is_verified,
            source_code_available=source_code_available,
            compiler_version=compiler_version,
            is_proxy=is_proxy,
            implementation_address=implementation_address,
            is_upgradeable=is_upgradeable,
            has_mint_function=has_mint_function,
            has_burn_function=has_burn_function,
            has_pause_function=has_pause_function,
            has_freeze_function=has_freeze_function,
            owner_address=owner_address,
            ownership_renounced=ownership_renounced,
            total_supply=total_supply,
            supply_change_24h=supply_change_24h,
            supply_change_7d=supply_change_7d,
            cross_chain_addresses=cross_chain_addresses,
            cross_chain_confidence=cross_chain_confidence,
            risk_flags=risk_flags,
            contract_risk_score=contract_risk_score
        )
    
    async def _get_total_supply(self, address: str) -> Optional[float]:
        """Query totalSupply() from contract."""
        try:
            total_supply_sig = self.web3.keccak(text="totalSupply()")[:4].hex()
            result = self.web3.eth.call({"to": address, "data": total_supply_sig})
            supply_wei = int(result.hex(), 16)
            
            # Get decimals
            decimals_sig = self.web3.keccak(text="decimals()")[:4].hex()
            decimals_result = self.web3.eth.call({"to": address, "data": decimals_sig})
            decimals = int(decimals_result.hex(), 16)
            
            return supply_wei / (10 ** decimals)
        
        except Exception:
            return None
    
    def _calculate_risk_score(self, risk_flags: list) -> int:
        """
        Calculate 0-100 risk score from flags.
        0 = safe, 100 = critical risk.
        """
        if not risk_flags:
            return 0
        
        # Weighted sum of severities, capped at 100
        total_severity = sum(flag.severity for flag in risk_flags)
        
        # Normalize to 0-100 scale (assume max realistic severity sum ~50)
        risk_score = min(100, int((total_severity / 50) * 100))
        
        return risk_score
