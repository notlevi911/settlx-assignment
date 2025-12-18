"""
Liquidity Intel Service - DEX and CEX liquidity analysis.
Determines if token can be traded safely at size.
"""
from datetime import datetime
from typing import Dict, Optional
from app.core.models import LiquidityIntelResponse, CertainData, RiskFlagDetail
from app.core.enums import DataCertainty, RiskFlag
from app.services.dexscreener_client import DexScreenerClient


class LiquidityIntelService:
    """
    Analyzes token liquidity and tradability.
    Primarily PROVEN data from DEX APIs, with INFERRED slippage estimates.
    """
    
    # Thresholds for risk flags
    LOW_LIQUIDITY_THRESHOLD_USD = 100_000
    LOW_VOLUME_THRESHOLD_USD = 50_000
    HIGH_CONCENTRATION_THRESHOLD_PCT = 80  # % in top pool
    HIGH_SLIPPAGE_THRESHOLD_PCT = 5  # % for $10k trade
    
    def __init__(self):
        self.dex_client = DexScreenerClient()
    
    async def analyze_liquidity(self, chain: str, address: str) -> LiquidityIntelResponse:
        """
        Full liquidity analysis pipeline.
        Classifies all data as PROVEN, INFERRED, or UNKNOWN.
        """
        risk_flags = []
        
        # Step 1: Fetch DEX pairs
        pairs_data = await self.dex_client.get_token_pairs(chain, address)
        
        if pairs_data.get("error"):
            # Cannot fetch data - return UNKNOWN response
            return self._build_unknown_response(chain, address, pairs_data["error"])
        
        pairs = pairs_data["pairs"]
        
        # Step 2: Liquidity statistics (PROVEN)
        liquidity_stats = self.dex_client.calculate_liquidity_stats(pairs)
        
        total_liquidity_usd = CertainData(
            value=liquidity_stats["total_liquidity_usd"],
            certainty=DataCertainty.PROVEN if liquidity_stats["total_liquidity_usd"] is not None else DataCertainty.UNKNOWN,
            source="DexScreener aggregated DEX data",
            reason=None if liquidity_stats["total_liquidity_usd"] is not None else "No DEX pairs found"
        )
        
        top_pool_liquidity_usd = CertainData(
            value=liquidity_stats["top_pool_liquidity_usd"],
            certainty=DataCertainty.PROVEN if liquidity_stats["top_pool_liquidity_usd"] is not None else DataCertainty.UNKNOWN,
            source="DexScreener aggregated DEX data",
            reason=None
        )
        
        pool_count = CertainData(
            value=liquidity_stats["pool_count"],
            certainty=DataCertainty.PROVEN,
            source="DexScreener API",
            reason=None
        )
        
        top_pool_percentage = CertainData(
            value=liquidity_stats["top_pool_percentage"],
            certainty=DataCertainty.PROVEN if liquidity_stats["top_pool_percentage"] is not None else DataCertainty.UNKNOWN,
            source="Calculated from DEX pair data",
            reason=None
        )
        
        liquidity_distribution = CertainData(
            value=liquidity_stats["liquidity_distribution"],
            certainty=DataCertainty.PROVEN,
            source="DexScreener pair data",
            reason=None
        )
        
        # Risk flag: Low liquidity
        if total_liquidity_usd.value and total_liquidity_usd.value < self.LOW_LIQUIDITY_THRESHOLD_USD:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.LOW_LIQUIDITY,
                evidence=f"Total DEX liquidity: ${total_liquidity_usd.value:,.0f} (below ${self.LOW_LIQUIDITY_THRESHOLD_USD:,})",
                severity=9,
                certainty=DataCertainty.PROVEN
            ))
        
        # Risk flag: Concentrated pools
        if top_pool_percentage.value and top_pool_percentage.value > self.HIGH_CONCENTRATION_THRESHOLD_PCT:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.CONCENTRATED_POOLS,
                evidence=f"{top_pool_percentage.value:.1f}% of liquidity in single pool (threshold: {self.HIGH_CONCENTRATION_THRESHOLD_PCT}%)",
                severity=6,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 3: Volume statistics (PROVEN)
        volume_stats = self.dex_client.calculate_volume_stats(pairs)
        
        volume_24h_usd = CertainData(
            value=volume_stats["volume_24h_usd"],
            certainty=DataCertainty.PROVEN if volume_stats["volume_24h_usd"] is not None else DataCertainty.UNKNOWN,
            source="DexScreener 24h volume data",
            reason=None
        )
        
        # 7d volume (UNKNOWN - not provided by DexScreener in this implementation)
        volume_7d_usd = CertainData(
            value=None,
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="7-day volume not available from DexScreener API"
        )
        
        volume_to_liquidity_ratio = CertainData(
            value=volume_stats["volume_to_liquidity_ratio"],
            certainty=DataCertainty.PROVEN if volume_stats["volume_to_liquidity_ratio"] is not None else DataCertainty.UNKNOWN,
            source="Calculated from 24h volume / liquidity",
            reason=None
        )
        
        # Risk flag: Low volume
        if volume_24h_usd.value and volume_24h_usd.value < self.LOW_VOLUME_THRESHOLD_USD:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.LOW_VOLUME,
                evidence=f"24h volume: ${volume_24h_usd.value:,.0f} (below ${self.LOW_VOLUME_THRESHOLD_USD:,})",
                severity=7,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 4: Slippage estimation (INFERRED)
        if total_liquidity_usd.value:
            slippage_1k = self.dex_client.estimate_slippage(
                total_liquidity_usd.value, 1_000
            )
            slippage_10k = self.dex_client.estimate_slippage(
                total_liquidity_usd.value, 10_000
            )
            slippage_100k = self.dex_client.estimate_slippage(
                total_liquidity_usd.value, 100_000
            )
            
            slippage_1k_usd = CertainData(
                value=slippage_1k,
                certainty=DataCertainty.INFERRED,
                source="Constant product AMM model approximation",
                reason="Estimated using simplified AMM curve (actual slippage may vary by DEX)"
            )
            
            slippage_10k_usd = CertainData(
                value=slippage_10k,
                certainty=DataCertainty.INFERRED,
                source="Constant product AMM model approximation",
                reason="Estimated using simplified AMM curve (actual slippage may vary by DEX)"
            )
            
            slippage_100k_usd = CertainData(
                value=slippage_100k,
                certainty=DataCertainty.INFERRED,
                source="Constant product AMM model approximation",
                reason="Estimated using simplified AMM curve (actual slippage may vary by DEX)"
            )
            
            # Risk flag: High slippage
            if slippage_10k > self.HIGH_SLIPPAGE_THRESHOLD_PCT:
                risk_flags.append(RiskFlagDetail(
                    flag=RiskFlag.HIGH_SLIPPAGE,
                    evidence=f"Estimated {slippage_10k:.2f}% slippage for $10k trade (threshold: {self.HIGH_SLIPPAGE_THRESHOLD_PCT}%)",
                    severity=8,
                    certainty=DataCertainty.INFERRED
                ))
        else:
            slippage_1k_usd = CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason="No liquidity data")
            slippage_10k_usd = CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason="No liquidity data")
            slippage_100k_usd = CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason="No liquidity data")
        
        # Step 5: CEX listings (UNKNOWN - not implemented)
        cex_listings = CertainData(
            value=[],
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="CEX listing detection not implemented (requires CEX API integrations)"
        )
        
        cex_volume_24h_usd = CertainData(
            value=None,
            certainty=DataCertainty.UNKNOWN,
            source=None,
            reason="CEX volume tracking not implemented"
        )
        
        # Risk flag: No CEX support (if only DEX liquidity is low)
        if total_liquidity_usd.value and total_liquidity_usd.value < 500_000:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.NO_CEX_SUPPORT,
                evidence="No CEX listings detected and low DEX liquidity",
                severity=6,
                certainty=DataCertainty.INFERRED
            ))
        
        # Step 6: Calculate liquidity risk score
        liquidity_risk_score = self._calculate_liquidity_risk(
            risk_flags,
            total_liquidity_usd.value,
            volume_24h_usd.value
        )
        
        return LiquidityIntelResponse(
            chain=chain,
            address=address,
            timestamp=datetime.utcnow(),
            total_liquidity_usd=total_liquidity_usd,
            top_pool_liquidity_usd=top_pool_liquidity_usd,
            pool_count=pool_count,
            volume_24h_usd=volume_24h_usd,
            volume_7d_usd=volume_7d_usd,
            volume_to_liquidity_ratio=volume_to_liquidity_ratio,
            top_pool_percentage=top_pool_percentage,
            liquidity_distribution=liquidity_distribution,
            slippage_1k_usd=slippage_1k_usd,
            slippage_10k_usd=slippage_10k_usd,
            slippage_100k_usd=slippage_100k_usd,
            cex_listings=cex_listings,
            cex_volume_24h_usd=cex_volume_24h_usd,
            risk_flags=risk_flags,
            liquidity_risk_score=liquidity_risk_score
        )
    
    def _build_unknown_response(self, chain: str, address: str, error: str) -> LiquidityIntelResponse:
        """Build response when liquidity data is unavailable."""
        unknown_reason = f"DexScreener API error: {error}"
        
        return LiquidityIntelResponse(
            chain=chain,
            address=address,
            timestamp=datetime.utcnow(),
            total_liquidity_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            top_pool_liquidity_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            pool_count=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            volume_24h_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            volume_7d_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            volume_to_liquidity_ratio=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            top_pool_percentage=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            liquidity_distribution=CertainData(value={}, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            slippage_1k_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            slippage_10k_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            slippage_100k_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            cex_listings=CertainData(value=[], certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            cex_volume_24h_usd=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            risk_flags=[],
            liquidity_risk_score=50  # Unknown = medium risk
        )
    
    def _calculate_liquidity_risk(
        self,
        risk_flags: list,
        liquidity: Optional[float],
        volume: Optional[float]
    ) -> int:
        """
        Calculate 0-100 liquidity risk score.
        0 = excellent liquidity, 100 = illiquid/untradeable.
        """
        base_score = sum(flag.severity for flag in risk_flags) * 2
        
        # Adjust based on absolute liquidity
        if liquidity is not None:
            if liquidity < 50_000:
                base_score += 30
            elif liquidity < 100_000:
                base_score += 20
            elif liquidity < 500_000:
                base_score += 10
            elif liquidity > 5_000_000:
                base_score -= 10
        
        # Adjust based on volume
        if volume is not None:
            if volume < 10_000:
                base_score += 15
            elif volume < 50_000:
                base_score += 10
        
        return min(100, max(0, base_score))
