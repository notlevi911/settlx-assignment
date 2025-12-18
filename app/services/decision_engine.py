"""
Decision Engine - Consolidates all analyses into final listing decision.
Combines contract, social, and liquidity intel into actionable recommendation.
"""
from typing import List, Tuple
from app.core.models import (
    FinalDecisionResponse,
    ContractTruthResponse,
    SocialIntelResponse,
    LiquidityIntelResponse,
    RiskFlagDetail
)
from app.core.enums import DecisionHint, DataCertainty, RiskFlag


class DecisionEngine:
    """
    Consolidates all three analysis streams into final decision.
    Outputs: LIST, LIST_WITH_LIMITS, DO_NOT_LIST, or NEEDS_REVIEW.
    """
    
    # Critical flags that block listing
    CRITICAL_FLAGS = {
        RiskFlag.UNVERIFIED_CONTRACT,
        RiskFlag.UPGRADEABLE_PROXY,
        RiskFlag.PAUSABLE,
        RiskFlag.FREEZABLE,
    }
    
    # Flags that require position limits
    WARNING_FLAGS = {
        RiskFlag.MINTABLE,
        RiskFlag.LOW_LIQUIDITY,
        RiskFlag.HIGH_SLIPPAGE,
        RiskFlag.OWNERSHIP_NOT_RENOUNCED,
    }
    
    # Risk score thresholds
    DO_NOT_LIST_THRESHOLD = 70
    LIST_WITH_LIMITS_THRESHOLD = 40
    
    def make_decision(
        self,
        contract: ContractTruthResponse,
        social: SocialIntelResponse,
        liquidity: LiquidityIntelResponse
    ) -> FinalDecisionResponse:
        """
        Consolidate all analyses and generate final decision.
        """
        # Aggregate all risk flags
        all_flags = contract.risk_flags + social.risk_flags + liquidity.risk_flags
        
        # Calculate overall risk score (weighted average)
        overall_risk_score = self._calculate_overall_risk(
            contract.contract_risk_score,
            social.narrative_risk_score,
            liquidity.liquidity_risk_score
        )
        
        # Identify critical unknowns
        critical_unknowns = self._identify_critical_unknowns(contract, social, liquidity)
        
        # Make decision
        decision, reasoning = self._determine_decision(
            overall_risk_score,
            all_flags,
            critical_unknowns
        )
        
        return FinalDecisionResponse(
            token_address=contract.address,
            chain=contract.chain,
            symbol=social.symbol,
            timestamp=contract.timestamp,
            contract_risk_score=contract.contract_risk_score,
            liquidity_risk_score=liquidity.liquidity_risk_score,
            narrative_risk_score=social.narrative_risk_score,
            overall_risk_score=overall_risk_score,
            all_risk_flags=all_flags,
            decision=decision,
            decision_reasoning=reasoning,
            critical_unknowns=critical_unknowns
        )
    
    def _calculate_overall_risk(
        self,
        contract_score: int,
        narrative_score: int,
        liquidity_score: int
    ) -> int:
        """
        Weighted average of risk scores.
        Contract safety is most important, then liquidity, then narrative.
        """
        weights = {
            "contract": 0.50,  # 50% weight
            "liquidity": 0.35,  # 35% weight
            "narrative": 0.15,  # 15% weight
        }
        
        weighted_score = (
            contract_score * weights["contract"] +
            liquidity_score * weights["liquidity"] +
            narrative_score * weights["narrative"]
        )
        
        return int(weighted_score)
    
    def _identify_critical_unknowns(
        self,
        contract: ContractTruthResponse,
        social: SocialIntelResponse,
        liquidity: LiquidityIntelResponse
    ) -> List[str]:
        """
        Identify UNKNOWN data points that are critical for decision making.
        """
        unknowns = []
        
        # Critical contract unknowns
        if contract.is_verified.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Contract verification status unknown")
        
        if contract.is_upgradeable.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Contract upgradeability unknown")
        
        if contract.has_mint_function.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Mint function presence unknown (source code unavailable)")
        
        # Critical liquidity unknowns
        if liquidity.total_liquidity_usd.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Total liquidity unknown")
        
        if liquidity.volume_24h_usd.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Trading volume unknown")
        
        # Social unknowns are less critical but note them
        if social.news_count_24h.certainty == DataCertainty.UNKNOWN:
            unknowns.append("Social/news data unavailable (not critical)")
        
        return unknowns
    
    def _determine_decision(
        self,
        overall_risk_score: int,
        risk_flags: List[RiskFlagDetail],
        critical_unknowns: List[str]
    ) -> Tuple[DecisionHint, str]:
        """
        Determine final decision based on risk score, flags, and unknowns.
        Returns: (decision, reasoning)
        """
        # Extract flag types
        flag_types = {flag.flag for flag in risk_flags}
        
        # Check for critical unknowns
        critical_unknowns_blocking = [
            u for u in critical_unknowns
            if "unknown" in u.lower() and "not critical" not in u.lower()
        ]
        
        if len(critical_unknowns_blocking) >= 3:
            return (
                DecisionHint.NEEDS_REVIEW,
                f"Too many critical unknowns ({len(critical_unknowns_blocking)}) prevent automated decision. Manual review required."
            )
        
        # Check for critical flags
        critical_flags_present = flag_types.intersection(self.CRITICAL_FLAGS)
        
        if critical_flags_present:
            critical_names = [f.value for f in critical_flags_present]
            return (
                DecisionHint.DO_NOT_LIST,
                f"Critical risk flags detected: {', '.join(critical_names)}. Contract unsafe for listing."
            )
        
        # Check overall risk score
        if overall_risk_score >= self.DO_NOT_LIST_THRESHOLD:
            return (
                DecisionHint.DO_NOT_LIST,
                f"Overall risk score {overall_risk_score}/100 exceeds threshold ({self.DO_NOT_LIST_THRESHOLD}). Risk too high for listing."
            )
        
        # Check for warning flags
        warning_flags_present = flag_types.intersection(self.WARNING_FLAGS)
        
        if warning_flags_present or overall_risk_score >= self.LIST_WITH_LIMITS_THRESHOLD:
            warning_names = [f.value for f in warning_flags_present]
            return (
                DecisionHint.LIST_WITH_LIMITS,
                f"Moderate risk detected (score: {overall_risk_score}/100). List with reduced position limits. Flags: {', '.join(warning_names) if warning_names else 'none specific'}"
            )
        
        # Safe to list
        return (
            DecisionHint.LIST,
            f"Low risk assessment (score: {overall_risk_score}/100). Contract appears safe for standard listing."
        )
