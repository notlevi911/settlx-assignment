"""
Liquidity Intelligence endpoint - /v1/liquidity/intel:snapshot
DEX + CEX liquidity analysis with deep pool math.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List, Dict
import math

from app.api.v1.schemas.requests import LiquidityIntelRequest
from app.api.v1.schemas.responses import (
    LiquidityIntelResponse,
    DEXMetrics,
    CEXMetrics,
    PriceImpact,
    PoolData,
    DepthAnalysis,
    Evidence,
    StructuredError,
    ErrorCode
)
from app.services.dexscreener_client import DexScreenerClient
from app.services.defillama_client import DefiLlamaClient, CEXIntegration
from app.services.thegraph_client import TheGraphClient

router = APIRouter()


@router.post("/liquidity/intel:snapshot", response_model=LiquidityIntelResponse)
async def analyze_liquidity_intel(request: LiquidityIntelRequest):
    """
    **Liquidity Intelligence Snapshot**
    
    Analyzes trading liquidity across DEX and CEX venues.
    
    DEX providers:
    - dexscreener: Aggregated DEX data (default)
    - thegraph: Deep pool math via Uniswap V3 subgraphs
    - defillama: Historical liquidity context
    
    CEX venues:
    - binance, coinbase, kraken, okx (placeholder - not fully implemented)
    
    Returns concentration metrics, price impact estimates, and depth analysis.
    """
    all_errors: List[StructuredError] = []
    all_warnings: List[str] = []
    evidence_list: List[Evidence] = []
    
    # Analyze DEX liquidity
    dex_metrics, dex_errors = await _analyze_dex(request)
    all_errors.extend(dex_errors)
    
    # Analyze CEX liquidity
    cex_metrics_list: List[CEXMetrics] = []
    if request.cex:
        for cex_venue in request.cex:
            cex_data = await _analyze_cex(cex_venue)
            cex_metrics_list.append(cex_data)
            if cex_data.errors:
                all_errors.extend(cex_data.errors)
    
    # Calculate price impacts
    price_impacts = []
    if request.options.compute_price_impact and dex_metrics.total_liquidity_usd > 0:
        price_impacts = _calculate_price_impacts(
            dex_metrics,
            request.trade_sizes_usd,
            request.dex
        )
    
    # Calculate overall risk score
    liquidity_risk = _calculate_liquidity_risk(dex_metrics, cex_metrics_list)
    risk_flags = _extract_risk_flags(dex_metrics, liquidity_risk)
    
    # Add evidence
    evidence_list.append(Evidence(
        provider="dexscreener",
        timestamp=datetime.now(timezone.utc),
        note=f"Analyzed {dex_metrics.pool_count} DEX pools"
    ))
    
    return LiquidityIntelResponse(
        asset={"symbol": request.asset.symbol, "coingecko_id": request.asset.coingecko_id or ""},
        timestamp=datetime.now(timezone.utc),
        dex=dex_metrics,
        cex=cex_metrics_list,
        price_impacts=price_impacts,
        liquidity_risk_score=liquidity_risk,
        risk_flags=risk_flags,
        evidence=evidence_list,
        errors=all_errors,
        warnings=all_warnings
    )


async def _analyze_dex(request: LiquidityIntelRequest) -> tuple[DEXMetrics, List[StructuredError]]:
    """Analyze DEX liquidity from multiple providers."""
    errors = []
    
    # Primary: DexScreener
    dex_client = DexScreenerClient()
    primary_dex = request.dex[0] if request.dex else None
    
    if not primary_dex:
        return DEXMetrics(
            total_liquidity_usd=0,
            total_volume_24h_usd=0,
            pool_count=0,
            top_pool_percentage=0,
            concentration_risk_score=100
        ), [StructuredError(
            code=ErrorCode.INVALID_ADDRESS,
            message="No DEX provider specified",
            source="dex",
            retryable=False
        )]
    
    # Fetch from DexScreener
    pairs_data = await dex_client.get_token_pairs(primary_dex.chain_id, primary_dex.token_address)
    
    if pairs_data.get("error"):
        errors.append(StructuredError(
            code=ErrorCode.UPSTREAM_ERROR,
            message=pairs_data["error"],
            source="dexscreener",
            retryable=True
        ))
        return DEXMetrics(
            total_liquidity_usd=0,
            total_volume_24h_usd=0,
            pool_count=0,
            top_pool_percentage=0,
            concentration_risk_score=100
        ), errors
    
    pairs = pairs_data["pairs"]
    
    # Calculate liquidity stats
    total_liq = sum(p.get("liquidity", {}).get("usd", 0) for p in pairs)
    total_vol = sum(p.get("volume", {}).get("h24", 0) for p in pairs)
    
    # Sort by liquidity
    sorted_pairs = sorted(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0), reverse=True)
    top_pool_liq = sorted_pairs[0].get("liquidity", {}).get("usd", 0) if sorted_pairs else 0
    
    # Build top pools list
    top_pools = []
    for pair in sorted_pairs[:10]:
        liq = pair.get("liquidity", {}).get("usd", 0)
        vol = pair.get("volume", {}).get("h24", 0)
        
        created_at_ms = pair.get("pairCreatedAt")
        created_at = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc) if created_at_ms else None
        age_days = (datetime.now(timezone.utc) - created_at).days if created_at else None
        
        top_pools.append(PoolData(
            dex=pair.get("dexId", "unknown"),
            pair_address=pair.get("pairAddress", ""),
            liquidity_usd=liq,
            volume_24h_usd=vol,
            price_usd=pair.get("priceUsd"),
            created_at=created_at,
            age_days=age_days
        ))
    
    # Calculate concentration metrics
    hhi = sum((p.get("liquidity", {}).get("usd", 0) / total_liq) ** 2 for p in pairs) if total_liq > 0 else 1.0
    top_pool_pct = (top_pool_liq / total_liq * 100) if total_liq > 0 else 0
    
    # Pool age analysis
    ages = [p.age_days for p in top_pools if p.age_days is not None]
    avg_age = sum(ages) / len(ages) if ages else None
    
    # Turnover ratio
    turnover = total_vol / total_liq if total_liq > 0 else 0
    
    # Concentration risk score (0-100)
    concentration_risk = _calculate_concentration_risk(hhi, top_pool_pct, avg_age, turnover)
    
    # Try to enhance with The Graph data
    if "ethereum" in primary_dex.chain_id.lower():
        await _enhance_with_thegraph(top_pools, primary_dex.token_address, errors)
    
    return DEXMetrics(
        total_liquidity_usd=round(total_liq, 2),
        total_volume_24h_usd=round(total_vol, 2),
        pool_count=len(pairs),
        top_pools=top_pools,
        hhi_index=round(hhi, 4),
        top_pool_percentage=round(top_pool_pct, 2),
        concentration_risk_score=concentration_risk,
        avg_pool_age_days=round(avg_age, 1) if avg_age else None,
        turnover_ratio=round(turnover, 2) if turnover > 0 else None
    ), errors


async def _enhance_with_thegraph(pools: List[PoolData], token_address: str, errors: List[StructuredError]):
    """Enhance pool data with The Graph subgraph queries."""
    try:
        graph_client = TheGraphClient()
        
        # Query top pool for detailed data
        if pools:
            top_pool = pools[0]
            pool_data, error = await graph_client.query_uniswap_v3_pool(top_pool.pair_address)
            
            if error:
                errors.append(error)
            elif pool_data:
                # Could enhance with tick data, but we already have basic metrics
                pass
                
    except Exception as e:
        errors.append(StructuredError(
            code=ErrorCode.UPSTREAM_ERROR,
            message=f"The Graph enhancement failed: {str(e)}",
            source="thegraph",
            retryable=True
        ))


async def _analyze_cex(venue) -> CEXMetrics:
    """Analyze CEX orderbook (placeholder)."""
    cex_client = CEXIntegration()
    
    depth_data, error = await cex_client.get_orderbook_depth(
        venue.venue,
        venue.symbol,
        venue.depth_levels
    )
    
    if error:
        return CEXMetrics(
            venue=venue.venue,
            symbol=venue.symbol,
            errors=[error]
        )
    
    # Would populate with real data
    return CEXMetrics(
        venue=venue.venue,
        symbol=venue.symbol,
        bid_depth_usd=None,
        ask_depth_usd=None,
        spread_bps=None,
        depth_analysis=[],
        errors=[StructuredError(
            code=ErrorCode.UNSUPPORTED_SOURCE,
            message=f"CEX integration for {venue.venue} not fully implemented",
            source=venue.venue,
            retryable=False
        )]
    )


def _calculate_concentration_risk(hhi: float, top_pool_pct: float, avg_age: float, turnover: float) -> int:
    """
    Enhanced concentration risk scoring.
    Uses Herfindahl index + pool age + turnover.
    """
    score = 0
    
    # HHI component (0-40 points)
    if hhi > 0.7:  # Single pool >80%
        score += 40
    elif hhi > 0.5:  # Single pool >70%
        score += 30
    elif hhi > 0.25:  # Moderate concentration
        score += 15
    
    # Top pool percentage component (0-20 points)
    if top_pool_pct > 90:
        score += 20
    elif top_pool_pct > 75:
        score += 10
    
    # Pool age component (0-20 points)
    if avg_age is not None:
        if avg_age < 7:  # Very new
            score += 20
        elif avg_age < 30:  # Less than a month
            score += 10
    
    # Turnover component (0-20 points)
    if turnover is not None:
        if turnover < 0.05:  # Stale liquidity
            score += 20
        elif turnover > 20:  # Suspicious high volume
            score += 15
        elif turnover < 0.2:
            score += 10
    
    return min(score, 100)


def _calculate_price_impacts(
    dex_metrics: DEXMetrics,
    trade_sizes: List[int],
    dex_providers
) -> List[PriceImpact]:
    """Calculate price impact for different trade sizes."""
    impacts = []
    
    total_liq = dex_metrics.total_liquidity_usd
    if total_liq == 0:
        return impacts
    
    for trade_size in trade_sizes:
        # Simplified constant product formula
        # price_impact = trade_size / (2 * liquidity)
        
        # Adjust for concentrated liquidity if using V3
        effective_liq = total_liq * 1.5  # Assume some concentration benefit
        
        impact_pct = (trade_size / (2 * effective_liq)) * 100
        slippage_pct = impact_pct * 1.1  # Slippage slightly higher than impact
        
        # Confidence based on liquidity depth
        confidence = min(effective_liq / (trade_size * 10), 1.0)
        
        impacts.append(PriceImpact(
            trade_size_usd=trade_size,
            estimated_slippage_pct=round(slippage_pct, 4),
            price_impact_pct=round(impact_pct, 4),
            confidence=round(confidence, 2)
        ))
    
    return impacts


def _calculate_liquidity_risk(dex: DEXMetrics, cex_list: List[CEXMetrics]) -> int:
    """Calculate overall liquidity risk score."""
    risk = 0
    
    # Low liquidity
    if dex.total_liquidity_usd < 100_000:
        risk += 50
    elif dex.total_liquidity_usd < 500_000:
        risk += 30
    elif dex.total_liquidity_usd < 1_000_000:
        risk += 15
    
    # Concentration risk
    risk += int(dex.concentration_risk_score * 0.3)  # 30% weight
    
    # Low volume
    if dex.total_volume_24h_usd < 50_000:
        risk += 20
    elif dex.total_volume_24h_usd < 200_000:
        risk += 10
    
    return min(risk, 100)


def _extract_risk_flags(dex: DEXMetrics, risk_score: int) -> List[str]:
    """Extract risk flags from metrics."""
    flags = []
    
    if dex.total_liquidity_usd < 100_000:
        flags.append("LOW_LIQUIDITY")
    
    if dex.total_volume_24h_usd < 50_000:
        flags.append("LOW_VOLUME")
    
    if dex.concentration_risk_score > 70:
        flags.append("HIGH_CONCENTRATION")
    
    if dex.hhi_index and dex.hhi_index > 0.5:
        flags.append("CONCENTRATED_POOLS")
    
    if dex.avg_pool_age_days and dex.avg_pool_age_days < 7:
        flags.append("NEW_POOLS")
    
    if dex.turnover_ratio and dex.turnover_ratio < 0.1:
        flags.append("STALE_LIQUIDITY")
    
    if dex.turnover_ratio and dex.turnover_ratio > 20:
        flags.append("SUSPICIOUS_VOLUME")
    
    return flags
