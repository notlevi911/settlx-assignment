"""
Pydantic models for request/response schemas.
All models enforce the PROVEN/INFERRED/UNKNOWN classification.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from .enums import DataCertainty, RiskFlag, DecisionHint


class CertainData(BaseModel):
    """Wrapper for any data point with certainty classification."""
    value: Any
    certainty: DataCertainty
    source: Optional[str] = None  # Evidence: which API/contract/method
    reason: Optional[str] = None  # Why UNKNOWN or INFERRED


class RiskFlagDetail(BaseModel):
    """A risk flag with evidence and impact."""
    flag: RiskFlag
    evidence: str  # Source of detection (e.g., "contract function mint() found")
    severity: int = Field(..., ge=1, le=10)  # 1=low, 10=critical
    certainty: DataCertainty


class ContractTruthResponse(BaseModel):
    """Response for /contract/{chain}/{address}"""
    chain: str
    address: str
    timestamp: datetime
    
    # Contract verification
    is_verified: CertainData
    source_code_available: CertainData
    compiler_version: CertainData
    
    # Proxy detection
    is_proxy: CertainData
    implementation_address: CertainData
    is_upgradeable: CertainData
    
    # Admin powers
    has_mint_function: CertainData
    has_burn_function: CertainData
    has_pause_function: CertainData
    has_freeze_function: CertainData
    
    # Ownership
    owner_address: CertainData
    ownership_renounced: CertainData
    
    # Supply tracking
    total_supply: CertainData
    supply_change_24h: CertainData
    supply_change_7d: CertainData
    
    # Cross-chain
    cross_chain_addresses: CertainData
    cross_chain_confidence: CertainData
    
    # Risk summary
    risk_flags: List[RiskFlagDetail]
    contract_risk_score: int = Field(..., ge=0, le=100)  # 0=safe, 100=critical


class SocialIntelResponse(BaseModel):
    """Response for /social/{symbol}"""
    symbol: str
    timestamp: datetime
    
    # News volume
    news_count_24h: CertainData
    news_count_7d: CertainData
    
    # Sentiment
    sentiment_score: CertainData
    sentiment_distribution: CertainData
    
    # Attention
    attention_spike_detected: CertainData
    attention_percentile: CertainData
    
    # Coordination
    source_diversity: CertainData
    narrative_keywords: CertainData
    
    # Risk summary
    risk_flags: List[RiskFlagDetail]
    narrative_risk_score: int = Field(..., ge=0, le=100)


class LiquidityIntelResponse(BaseModel):
    """Response for /liquidity/{chain}/{address}"""
    chain: str
    address: str
    timestamp: datetime
    
    # DEX liquidity
    total_liquidity_usd: CertainData
    top_pool_liquidity_usd: CertainData
    pool_count: CertainData
    
    # Volume
    volume_24h_usd: CertainData
    volume_7d_usd: CertainData
    volume_to_liquidity_ratio: CertainData
    
    # Concentration
    top_pool_percentage: CertainData
    liquidity_distribution: CertainData
    
    # Slippage (estimated)
    slippage_1k_usd: CertainData
    slippage_10k_usd: CertainData
    slippage_100k_usd: CertainData
    
    # CEX presence
    cex_listings: CertainData
    cex_volume_24h_usd: CertainData
    
    # Risk summary
    risk_flags: List[RiskFlagDetail]
    liquidity_risk_score: int = Field(..., ge=0, le=100)


class FinalDecisionResponse(BaseModel):
    """Consolidated decision across all three endpoints."""
    token_address: str
    chain: str
    symbol: Optional[str]
    timestamp: datetime
    
    # Component scores
    contract_risk_score: int
    liquidity_risk_score: int
    narrative_risk_score: int
    
    # Aggregate
    overall_risk_score: int = Field(..., ge=0, le=100)
    all_risk_flags: List[RiskFlagDetail]
    
    # Decision
    decision: DecisionHint
    decision_reasoning: str  # Human-readable explanation
    
    # Blockers (UNKNOWN data that prevents confident decision)
    critical_unknowns: List[str]
