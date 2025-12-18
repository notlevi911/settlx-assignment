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


# ===== Contract Truth Response (Strict Spec) =====

# Verification data
class VerificationData(BaseModel):
    """Contract verification information."""
    verified_source: bool
    explorer: str = Field(..., description="etherscan|snowtrace|solscan|other")
    abi_available: bool
    source_hash: Optional[str] = Field(None, description="sha256:...")


# Code identity
class CodeIdentity(BaseModel):
    """Code identity information."""
    runtime_code_hash: Optional[str] = Field(None, description="keccak256:...")
    deployer: Optional[str] = None
    creation_tx: Optional[str] = None


# Upgradeability data
class UpgradeabilityData(BaseModel):
    """Proxy and upgradeability information."""
    is_proxy: bool
    proxy_type: Optional[str] = Field(None, description="uups|transparent|beacon|unknown|null")
    implementation: Optional[str] = None
    admin: Optional[str] = None
    admin_is_contract: Optional[bool] = None
    timelock_detected: bool = False
    upgrade_authority: Optional[str] = None


# Fee controls
class FeeControls(BaseModel):
    """Fee control capabilities."""
    can_change_fees: bool
    max_fee_bps: Optional[int] = None


# Controls data
class ControlsData(BaseModel):
    """Token control capabilities."""
    owner_or_admin: Optional[str] = None
    can_mint: Optional[bool] = None
    can_burn: Optional[bool] = None
    can_pause: Optional[bool] = None
    can_blacklist_or_freeze: Optional[bool] = None
    fee_controls: FeeControls


# Supply activity
class SupplyActivity(BaseModel):
    """Supply activity metrics."""
    mint_events_lookback: Optional[int] = None
    mint_amount_lookback: Optional[str] = None
    burn_events_lookback: Optional[int] = None
    burn_amount_lookback: Optional[str] = None


# Risk flag
class RiskFlag(BaseModel):
    """Risk flag."""
    id: str = Field(..., description="MINT_PRIVILEGE|PROXY_UPGRADEABLE|UPGRADEABLE_NO_TIMELOCK_EVIDENCE|FREEZE_AUTHORITY_PRESENT|UPGRADE_AUTHORITY_PRESENT")
    severity: str = Field(..., description="low|medium|high")
    why: str


# Instance data (PROVEN)
class ProvenInstance(BaseModel):
    """Proven facts about a chain instance."""
    chain: str
    address: str
    type: str = Field(..., description="erc20|spl")
    verification: VerificationData
    code_identity: CodeIdentity
    upgradeability: UpgradeabilityData
    controls: ControlsData
    supply_activity: SupplyActivity
    risk_flags: List[RiskFlag] = Field(default=[])


# Cross-chain equivalence (INFERRED)
class CrossChainEquivalence(BaseModel):
    """Cross-chain asset equivalence analysis."""
    pair: List[str] = Field(..., description="['chain:address', 'chain:address']")
    confidence: float = Field(..., ge=0, le=1)
    reasons: List[str]
    label: str = Field(..., description="proven_same_asset|likely_same_asset|unknown")


# Proven section
class ProvenSection(BaseModel):
    """Proven facts section."""
    instances: List[ProvenInstance]


# Inferred section
class InferredSection(BaseModel):
    """Inferred analysis section."""
    cross_chain_equivalence: List[CrossChainEquivalence] = Field(default=[])


# Data section wrapper
class ContractTruthDataSection(BaseModel):
    """Data section with PROVEN vs INFERRED separation."""
    proven: ProvenSection
    inferred: InferredSection


# Strict spec response
class ContractTruthResponse(BaseModel):
    """Response for /v1/contracts/truth:analyze (strict spec)."""
    request_id: str
    as_of: str = Field(..., description="ISO timestamp")
    data: ContractTruthDataSection
    evidence: List[Evidence] = Field(default=[])
    warnings: List[str] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])


# ===== Social Signal Response =====

# Source-level sentiment
class SourceSentiment(BaseModel):
    """Sentiment for a single source."""
    score: Optional[float] = Field(None, ge=-1, le=1)
    volume: int = Field(..., ge=0)
    engagement: int = Field(default=0, ge=0)
    status: str = Field(..., description="ok|partial|unsupported")


class BySourceSentiment(BaseModel):
    """Sentiment breakdown by source."""
    news: Optional[SourceSentiment] = None
    x: Optional[SourceSentiment] = None
    reddit: Optional[SourceSentiment] = None
    youtube: Optional[SourceSentiment] = None


# Mention velocity
class MentionVelocity(BaseModel):
    """Mention velocity with baseline comparison."""
    per_min: float = Field(..., ge=0)
    zscore_vs_30d: float


# Creator concentration
class CreatorConcentration(BaseModel):
    """Top creator concentration metric."""
    top_10_share: float = Field(..., ge=0, le=1)


# Top creator/influencer
class TopCreator(BaseModel):
    """Top influencer information."""
    handle: str
    followers: int = Field(default=0, ge=0)
    engagement: int = Field(..., ge=0)
    sentiment: float = Field(..., ge=-1, le=1)
    post_id: str
    source: str


# Anomaly detection
class Anomaly(BaseModel):
    """Detected anomaly."""
    type: str = Field(..., description="volume_spike|coordination_signal")
    severity: str = Field(..., description="low|medium|high")
    reason: str


# Top post with text hash
class TopPost(BaseModel):
    """Top post with deduplication hash."""
    source: str
    id: str
    url: str
    author: Optional[str] = None
    ts: str = Field(..., description="ISO timestamp")
    engagement: int = Field(..., ge=0)
    sentiment: float = Field(..., ge=-1, le=1)
    text_hash: str = Field(..., description="sha256:...")


# Main metrics
class SentimentMetrics(BaseModel):
    """Sentiment analysis metrics."""
    score: Optional[float] = Field(None, ge=-1, le=1, description="Overall sentiment: -1=negative, +1=positive")
    label: Optional[str] = Field(None, description="very_negative|negative|slightly_negative|neutral|slightly_positive|positive|very_positive")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in sentiment score")
    by_source: BySourceSentiment


class AttentionMetrics(BaseModel):
    """Attention and velocity metrics."""
    mention_velocity: MentionVelocity
    unique_authors: Optional[int] = Field(None, ge=0)
    creator_concentration: CreatorConcentration


class InfluencerPressure(BaseModel):
    """Influencer pressure metrics."""
    score: float = Field(..., ge=0, le=1)
    top_creators: List[TopCreator] = Field(default=[])


# Legacy schemas for compatibility
class SourceBreakdown(BaseModel):
    """Per-source analysis (legacy)."""
    source: str
    item_count: int
    sentiment_avg: Optional[float] = Field(None, ge=-1, le=1)
    top_keywords: List[str] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])


class CoordinationMetrics(BaseModel):
    """Coordination detection metrics (legacy)."""
    source_diversity_score: float = Field(..., ge=0, le=1)
    unique_sources: int
    total_sources: int
    suspected_coordination: bool
    evidence: List[str] = Field(default=[])


# Data section wrapper
class SocialDataSection(BaseModel):
    """Data section for strict spec compliance."""
    sentiment: SentimentMetrics
    attention: AttentionMetrics
    influencer_pressure: InfluencerPressure
    anomalies: List[Anomaly] = Field(default=[])
    top_posts: List[TopPost] = Field(default=[])


class SocialSentimentResponse(BaseModel):
    """Response for /v1/social/sentiment:score (strict spec)."""
    request_id: str
    as_of: str = Field(..., description="ISO timestamp")
    data: SocialDataSection
    evidence: List[Evidence] = Field(default=[])
    warnings: List[str] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])


# ===== Liquidity Intel Response =====

# Liquidity flags
class LiquidityFlag(BaseModel):
    """Liquidity risk flag."""
    type: str = Field(..., description="thin_depth|gap_risk|dex_liquidity_low|liquidity_concentrated")
    severity: str = Field(..., description="low|medium|high")
    reason: str


# Top pair/pool data
class TopPair(BaseModel):
    """Top DEX pair."""
    pair: str
    price_usd: float
    liquidity_usd: float
    volume_24h_usd: float
    fdv_usd: Optional[float] = None


# DEX data (strict spec)
class DEXData(BaseModel):
    """DEX liquidity data."""
    provider: str
    chainId: str
    pairs_found: int
    top_pairs: List[TopPair] = Field(default=[])
    flags: List[LiquidityFlag] = Field(default=[])


# CEX depth data
class CEXDepth(BaseModel):
    """CEX orderbook depth."""
    within_10bps_usd: Optional[float] = None
    within_25bps_usd: Optional[float] = None
    within_50bps_usd: Optional[float] = None


# CEX impact estimate
class ImpactEstimate(BaseModel):
    """CEX slippage estimate."""
    size_usd: int
    slippage_bps: float


# CEX data (strict spec)
class CEXData(BaseModel):
    """CEX orderbook data."""
    venue: str
    symbol: str
    mid_price: Optional[float] = None
    spread_bps: Optional[float] = None
    depth: CEXDepth
    impact_estimates: List[ImpactEstimate] = Field(default=[])
    flags: List[LiquidityFlag] = Field(default=[])


# Liquidity score
class LiquidityScore(BaseModel):
    """Overall liquidity score."""
    score: float = Field(..., ge=0, le=1)
    label: str = Field(..., description="low|medium|high")


# Data section wrapper
class LiquidityDataSection(BaseModel):
    """Data section for strict spec compliance."""
    cex: List[CEXData] = Field(default=[])
    dex: List[DEXData] = Field(default=[])
    liquidity_score: LiquidityScore


# Strict spec response
class LiquidityIntelResponse(BaseModel):
    """Response for /v1/liquidity/intel:snapshot (strict spec)."""
    request_id: str
    as_of: str = Field(..., description="ISO timestamp")
    data: LiquidityDataSection
    evidence: List[Evidence] = Field(default=[])
    warnings: List[str] = Field(default=[])
    errors: List[StructuredError] = Field(default=[])
