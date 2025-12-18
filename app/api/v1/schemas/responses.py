"""
Response schemas for v1 API endpoints.
Includes structured error handling.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ===== Error Handling =====

class ErrorCode(str, Enum):
    """Standardized error codes."""
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    UNSUPPORTED_CHAIN = "UNSUPPORTED_CHAIN"
    INVALID_ADDRESS = "INVALID_ADDRESS"
    MISSING_API_KEY = "MISSING_API_KEY"
    PARSE_ERROR = "PARSE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StructuredError(BaseModel):
    """Structured error for partial failures."""
    code: ErrorCode
    message: str
    source: Optional[str] = Field(None, description="Which provider/service failed")
    retryable: bool = Field(False, description="Whether client should retry")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class Evidence(BaseModel):
    """Evidence for a data point or decision."""
    provider: str = Field(..., description="Data source: etherscan, cryptopanic, dexscreener, etc.")
    timestamp: datetime
    request_hash: Optional[str] = Field(None, description="Hash of request for deduplication")
    ref: Optional[str] = Field(None, description="URL or reference to raw data")
    note: Optional[str] = Field(None, description="Human-readable note")


# ===== Contract Truth Response =====

class ProxyType(str, Enum):
    """Types of proxy contracts."""
    NOT_PROXY = "NOT_PROXY"
    EIP1967_TRANSPARENT = "EIP1967_TRANSPARENT"
    EIP1967_UUPS = "EIP1967_UUPS"
    EIP1822_UUPS = "EIP1822_UUPS"
    EIP897 = "EIP897"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class ControlExtraction(BaseModel):
    """Extracted admin controls from contract."""
    has_mint: Optional[bool] = None
    has_burn: Optional[bool] = None
    has_pause: Optional[bool] = None
    has_freeze: Optional[bool] = None
    has_blacklist: Optional[bool] = None
    has_upgrade: Optional[bool] = None
    owner_address: Optional[str] = None
    ownership_renounced: Optional[bool] = None


class ChainAnalysis(BaseModel):
    """Analysis result for a single chain instance."""
    chain: str
    address: str
    type: str
    
    # Verification
    is_verified: Optional[bool] = None
    verification_source: Optional[str] = None
    
    # Proxy
    proxy_type: ProxyType = ProxyType.NOT_PROXY
    implementation_address: Optional[str] = None
    is_upgradeable: Optional[bool] = None
    
    # Controls
    controls: ControlExtraction
    
    # Code
    code_hash: Optional[str] = None
    compiler_version: Optional[str] = None
    
    # Supply
    current_supply: Optional[float] = None
    supply_change_24h_pct: Optional[float] = None
    supply_change_7d_pct: Optional[float] = None
    
    # Evidence
    evidence: List[Evidence] = []
    
    # Certainty flags
    proven_fields: List[str] = Field(default=[], description="Fields with PROVEN certainty")
    inferred_fields: List[str] = Field(default=[], description="Fields with INFERRED certainty")
    unknown_fields: List[str] = Field(default=[], description="Fields that are UNKNOWN")


class ContractTruthResponse(BaseModel):
    """Response for /v1/contracts/truth:analyze"""
    token: Dict[str, str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    
    # Analysis per chain
    analyses: List[ChainAnalysis]
    
    # Cross-chain correlation
    cross_chain_consistent: Optional[bool] = Field(None, description="Are controls consistent across chains?")
    cross_chain_notes: List[str] = Field(default=[], description="Inconsistencies or warnings")
    
    # Overall risk
    overall_risk_score: int = Field(..., ge=0, le=100)
    critical_flags: List[str] = Field(default=[])
    
    # Errors
    errors: List[StructuredError] = Field(default=[])
    warnings: List[str] = Field(default=[])


# ===== Social Signal Response =====

class SourceBreakdown(BaseModel):
    """Per-source analysis."""
    source: str
    item_count: int
    sentiment_avg: Optional[float] = Field(None, ge=-1, le=1)
    top_keywords: List[str] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])


class TopPost(BaseModel):
    """Top post/article."""
    title: str
    url: Optional[str] = None
    source: str
    published_at: datetime
    sentiment: Optional[float] = Field(None, ge=-1, le=1)
    votes: Optional[Dict[str, int]] = None


class SentimentMetrics(BaseModel):
    """Sentiment analysis metrics."""
    score: Optional[float] = Field(None, ge=-1, le=1, description="Overall sentiment: -1=negative, +1=positive")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in sentiment score")
    distribution: Optional[Dict[str, int]] = Field(None, description="positive/neutral/negative counts")
    sample_size: int = Field(..., ge=0)


class AttentionMetrics(BaseModel):
    """Attention and anomaly detection."""
    baseline_daily_count: float
    current_daily_count: float
    spike_detected: bool
    percentile: Optional[float] = Field(None, ge=0, le=100)
    anomaly_score: float = Field(..., ge=0, le=100)


class CoordinationMetrics(BaseModel):
    """Coordination detection metrics."""
    source_diversity_score: float = Field(..., ge=0, le=1)
    unique_sources: int
    total_sources: int
    suspected_coordination: bool
    evidence: List[str] = Field(default=[])


class SocialSentimentResponse(BaseModel):
    """Response for /v1/social/sentiment:score"""
    asset: Dict[str, str]
    lookback: Dict[str, str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    
    # Metrics
    sentiment: SentimentMetrics
    attention: AttentionMetrics
    coordination: CoordinationMetrics
    
    # Breakdown
    by_source: List[SourceBreakdown]
    top_posts: List[TopPost] = Field(default=[])
    
    # Evidence
    evidence: List[Evidence] = Field(default=[])
    
    # Errors
    errors: List[StructuredError] = Field(default=[])
    warnings: List[str] = Field(default=[])


# ===== Liquidity Intel Response =====

class PoolData(BaseModel):
    """Individual pool/pair data."""
    dex: str
    pair_address: str
    liquidity_usd: float
    volume_24h_usd: float
    price_usd: Optional[float] = None
    created_at: Optional[datetime] = None
    age_days: Optional[int] = None


class DEXMetrics(BaseModel):
    """DEX liquidity metrics."""
    total_liquidity_usd: float
    total_volume_24h_usd: float
    pool_count: int
    top_pools: List[PoolData] = Field(default=[])
    
    # Concentration
    hhi_index: Optional[float] = Field(None, description="Herfindahl-Hirschman Index")
    top_pool_percentage: float
    concentration_risk_score: int = Field(..., ge=0, le=100)
    
    # Quality
    avg_pool_age_days: Optional[float] = None
    turnover_ratio: Optional[float] = Field(None, description="24h volume / liquidity")


class PriceImpact(BaseModel):
    """Price impact for trade sizes."""
    trade_size_usd: int
    estimated_slippage_pct: float
    price_impact_pct: float
    confidence: float = Field(..., ge=0, le=1, description="Model confidence")


class DepthAnalysis(BaseModel):
    """Orderbook depth analysis."""
    bps: int = Field(..., description="Basis points from mid price")
    depth_usd: float = Field(..., description="Liquidity within this BPS")


class CEXMetrics(BaseModel):
    """CEX orderbook metrics."""
    venue: str
    symbol: str
    bid_depth_usd: Optional[float] = None
    ask_depth_usd: Optional[float] = None
    spread_bps: Optional[float] = None
    depth_analysis: List[DepthAnalysis] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])


class LiquidityIntelResponse(BaseModel):
    """Response for /v1/liquidity/intel:snapshot"""
    asset: Dict[str, str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    
    # DEX metrics
    dex: DEXMetrics
    
    # CEX metrics
    cex: List[CEXMetrics] = Field(default=[])
    
    # Price impact
    price_impacts: List[PriceImpact] = Field(default=[])
    
    # Overall risk
    liquidity_risk_score: int = Field(..., ge=0, le=100)
    risk_flags: List[str] = Field(default=[])
    
    # Evidence
    evidence: List[Evidence] = Field(default=[])
    
    # Errors
    errors: List[StructuredError] = Field(default=[])
    warnings: List[str] = Field(default=[])
