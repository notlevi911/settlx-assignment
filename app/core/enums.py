"""
Core enums and types for the decision engine.
Defines the certainty classification and risk flags.
"""
from enum import Enum


class DataCertainty(str, Enum):
    """Every data point must be classified into exactly one category."""
    PROVEN = "PROVEN"       # Directly verifiable from on-chain data or trusted APIs
    INFERRED = "INFERRED"   # Best-guess or heuristic-based signals
    UNKNOWN = "UNKNOWN"     # Cannot be verified; returns null with explanation


class RiskFlag(str, Enum):
    """Binary risk flags with explicit evidence."""
    # Contract risks
    MINTABLE = "MINTABLE"
    BURNABLE = "BURNABLE"
    PAUSABLE = "PAUSABLE"
    FREEZABLE = "FREEZABLE"
    UPGRADEABLE_PROXY = "UPGRADEABLE_PROXY"
    UNVERIFIED_CONTRACT = "UNVERIFIED_CONTRACT"
    RECENT_SUPPLY_CHANGE = "RECENT_SUPPLY_CHANGE"
    ADMIN_KEYS_DETECTED = "ADMIN_KEYS_DETECTED"
    OWNERSHIP_NOT_RENOUNCED = "OWNERSHIP_NOT_RENOUNCED"
    
    # Liquidity risks
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    LOW_VOLUME = "LOW_VOLUME"
    HIGH_SLIPPAGE = "HIGH_SLIPPAGE"
    CONCENTRATED_POOLS = "CONCENTRATED_POOLS"
    NO_CEX_SUPPORT = "NO_CEX_SUPPORT"
    RECENT_LIQUIDITY_DROP = "RECENT_LIQUIDITY_DROP"
    
    # Social/narrative risks
    NEGATIVE_SENTIMENT = "NEGATIVE_SENTIMENT"
    LOW_ATTENTION = "LOW_ATTENTION"
    COORDINATED_NARRATIVE = "COORDINATED_NARRATIVE"
    RECENT_CONTROVERSY = "RECENT_CONTROVERSY"
    NO_SOCIAL_DATA = "NO_SOCIAL_DATA"


class DecisionHint(str, Enum):
    """Final recommendation for listing team."""
    LIST = "LIST"                           # Safe to list with standard parameters
    LIST_WITH_LIMITS = "LIST_WITH_LIMITS"   # List but with reduced position limits
    DO_NOT_LIST = "DO_NOT_LIST"             # Critical risks detected
    NEEDS_REVIEW = "NEEDS_REVIEW"           # Too much uncertainty, manual review required


class Chain(str, Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
