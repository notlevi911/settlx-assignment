"""
Request schemas for v1 API endpoints.
These match the strict specifications from the audit.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ===== Contract Truth Schemas =====

class TokenInfo(BaseModel):
    """Token metadata."""
    symbol: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = None


class ChainInstance(BaseModel):
    """Single chain instance of a token."""
    chain: str = Field(..., description="Chain name: ethereum, avalanche, solana, bsc, polygon, arbitrum")
    address: str = Field(..., description="Token address on this chain")
    type: str = Field(..., description="Token standard: erc20, spl, erc721, etc.")


class ContractTruthOptions(BaseModel):
    """Analysis options for contract truth."""
    fetch_verified_source: bool = True
    fetch_abi_or_idl: bool = True
    detect_proxy_or_upgradeability: bool = True
    extract_controls: bool = True
    compute_code_hash: bool = False


class ContractTruthRequest(BaseModel):
    """Request for /v1/contracts/truth:analyze"""
    token: TokenInfo
    instances: List[ChainInstance] = Field(..., min_items=1)
    lookback_days: int = Field(default=30, ge=1, le=365)
    options: ContractTruthOptions = Field(default_factory=ContractTruthOptions)


# ===== Social Signal Schemas =====

class AssetInfo(BaseModel):
    """Asset for social analysis."""
    symbol: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = None


class LookbackWindow(BaseModel):
    """Time window for social analysis."""
    from_time: datetime = Field(..., alias="from")
    to: datetime


class SocialOptions(BaseModel):
    """Options for social analysis."""
    language: List[str] = Field(default=["en"])
    dedupe: bool = True
    bot_filter: bool = False  # Not implemented yet
    return_top_posts: int = Field(default=20, ge=0, le=100)


class SocialLimits(BaseModel):
    """Limits for social data fetching."""
    max_items_per_source: int = Field(default=200, ge=1, le=1000)


class SocialSentimentRequest(BaseModel):
    """Request for /v1/social/sentiment:score"""
    asset: AssetInfo
    keywords: List[str] = Field(..., min_items=1)
    lookback: LookbackWindow
    sources: List[str] = Field(default=["news"], description="Supported: news. Unsupported: x, reddit, youtube")
    limits: SocialLimits = Field(default_factory=SocialLimits)
    options: SocialOptions = Field(default_factory=SocialOptions)


# ===== Liquidity Intel Schemas =====

class LiquidityAsset(BaseModel):
    """Asset for liquidity analysis."""
    symbol: str
    coingecko_id: Optional[str] = None


class CEXVenue(BaseModel):
    """CEX orderbook request."""
    venue: str = Field(..., description="Exchange name: binance, coinbase, kraken, etc.")
    symbol: str = Field(..., description="Trading pair symbol on exchange")
    depth_levels: List[int] = Field(default=[50, 200, 1000], description="USD depth levels to analyze")


class DEXProvider(BaseModel):
    """DEX data request."""
    provider: str = Field(default="dexscreener", description="Data provider: dexscreener, thegraph, defillama")
    chain_id: str = Field(..., alias="chainId", description="Chain identifier")
    token_address: str = Field(..., alias="tokenAddress")


class LiquidityOptions(BaseModel):
    """Options for liquidity analysis."""
    compute_price_impact: bool = True
    compute_depth_bps: List[int] = Field(default=[10, 25, 50], description="Basis points for depth analysis")


class LiquidityIntelRequest(BaseModel):
    """Request for /v1/liquidity/intel:snapshot"""
    asset: LiquidityAsset
    cex: List[CEXVenue] = Field(default=[])
    dex: List[DEXProvider] = Field(..., min_items=1)
    trade_sizes_usd: List[int] = Field(default=[1000, 10000, 100000])
    options: LiquidityOptions = Field(default_factory=LiquidityOptions)
