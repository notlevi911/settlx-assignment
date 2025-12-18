"""
Liquidity Intelligence endpoint - /v1/liquidity/intel:snapshot
DEX + CEX liquidity analysis with deep pool math (strict spec).
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import math
import uuid

from app.api.v1.schemas.requests import LiquidityIntelRequest
from app.api.v1.schemas.responses import (
    LiquidityIntelResponse,
    LiquidityDataSection,
    DEXData,
    CEXData,
    TopPair,
    CEXDepth,
    ImpactEstimate,
    LiquidityFlag,
    LiquidityScore,
    Evidence,
    StructuredError,
    ErrorCode
)
from app.services.dexscreener_client import DexScreenerClient
from app.services.defillama_client import DefiLlamaClient
from app.services.thegraph_client import TheGraphClient

router = APIRouter()


@router.post("/liquidity/intel:snapshot", response_model=LiquidityIntelResponse)
async def analyze_liquidity_intel(request: LiquidityIntelRequest):
    """
    **Liquidity Intelligence Snapshot (Strict Spec)**
    
    Returns DEX snapshot matching Dexscreener + optional CEX depth analysis.
    
    Free integrations:
    - Dexscreener: DEX pairs/liquidity/volume
    - DefiLlama: Context enrichment (price reference)
    - The Graph: Deeper pool math / price-impact proxy
    
    CEX: Returns structured errors if venue not supported.
    """
    all_errors: List[StructuredError] = []
    all_warnings: List[str] = []
    evidence_list: List[Evidence] = []
    
    # Analyze DEX liquidity
    dex_data_list: List[DEXData] = []
    total_dex_liquidity = 0.0
    total_dex_volume = 0.0
    
    if request.dex:
        for dex_req in request.dex:
            dex_data, dex_errs = await _analyze_dex_provider(dex_req)
            dex_data_list.append(dex_data)
            all_errors.extend(dex_errs)
            
            # Aggregate for scoring
            if dex_data.top_pairs:
                total_dex_liquidity += sum(p.liquidity_usd for p in dex_data.top_pairs)
                total_dex_volume += sum(p.volume_24h_usd for p in dex_data.top_pairs)
    
    # Optional: DefiLlama price enrichment
    if request.dex and request.dex[0]:
        llama_client = DefiLlamaClient()
        price, price_err = await llama_client.get_token_price(
            request.dex[0].chain_id,
            request.dex[0].token_address
        )
        if price:
            evidence_list.append(Evidence(
                provider="defillama",
                timestamp=datetime.now(timezone.utc),
                note=f"Price reference: ${price:.6f}"
            ))
        elif price_err and price_err.retryable:
            all_warnings.append(f"DefiLlama unavailable: {price_err.message}")
    
    # Optional: The Graph deep pool math
    if request.dex and request.options.compute_price_impact:
        graph_client = TheGraphClient()
        try:
            # Query for price impact proxy (if Uniswap V3 pool exists)
            pools = await graph_client.query_token_pools(
                request.dex[0].chain_id,
                request.dex[0].token_address
            )
            if pools:
                evidence_list.append(Evidence(
                    provider="thegraph",
                    timestamp=datetime.now(timezone.utc),
                    note=f"Queried {len(pools)} Uniswap V3 pools for deep math"
                ))
        except Exception as e:
            all_warnings.append(f"The Graph unavailable: {str(e)}")
    
    # Analyze CEX liquidity
    cex_data_list: List[CEXData] = []
    if request.cex:
        for cex_req in request.cex:
            cex_data = await _analyze_cex_venue(cex_req)
            cex_data_list.append(cex_data)
            if cex_data.flags:
                all_errors.extend([StructuredError(
                    code=ErrorCode.UNSUPPORTED_SOURCE,
                    message=f"CEX venue '{cex_req.venue}' not fully implemented",
                    source=cex_req.venue,
                    retryable=False
                ) for flag in cex_data.flags if flag.type == "thin_depth"])
    
    # Calculate liquidity score
    liquidity_score = _calculate_liquidity_score(
        total_dex_liquidity,
        total_dex_volume,
        dex_data_list,
        cex_data_list
    )
    
    # Build data section
    data = LiquidityDataSection(
        cex=cex_data_list,
        dex=dex_data_list,
        liquidity_score=liquidity_score
    )
    
    # Add evidence
    evidence_list.append(Evidence(
        provider="dexscreener",
        timestamp=datetime.now(timezone.utc),
        note=f"Analyzed {sum(d.pairs_found for d in dex_data_list)} total pairs"
    ))
    
    return LiquidityIntelResponse(
        request_id=str(uuid.uuid4()),
        as_of=datetime.now(timezone.utc).isoformat(),
        data=data,
        evidence=evidence_list,
        warnings=all_warnings,
        errors=all_errors
    )


# ===== Helper Functions =====

async def _analyze_dex_provider(dex_req) -> Tuple[DEXData, List[StructuredError]]:
    """
    Analyze DEX liquidity via Dexscreener.
    Returns pairs_found, top_pairs, and flags.
    """
    errors = []
    
    dex_client = DexScreenerClient()
    pairs_data = await dex_client.get_token_pairs(dex_req.chain_id, dex_req.token_address)
    
    if pairs_data.get("error"):
        errors.append(StructuredError(
            code=ErrorCode.UPSTREAM_ERROR,
            message=pairs_data["error"],
            source="dexscreener",
            retryable=True
        ))
        return DEXData(
            provider=dex_req.provider,
            chainId=dex_req.chain_id,
            pairs_found=0,
            top_pairs=[],
            flags=[LiquidityFlag(
                type="dex_liquidity_low",
                severity="high",
                reason="Failed to fetch DEX data"
            )]
        ), errors
    
    pairs = pairs_data.get("pairs", [])
    
    # Sort by liquidity
    sorted_pairs = sorted(
        pairs,
        key=lambda p: p.get("liquidity", {}).get("usd", 0),
        reverse=True
    )
    
    # Build top pairs
    top_pairs = []
    total_liquidity = 0.0
    for pair in sorted_pairs[:10]:
        liq = pair.get("liquidity", {}).get("usd", 0)
        vol = pair.get("volume", {}).get("h24", 0)
        price = pair.get("priceUsd")
        fdv = pair.get("fdv")
        
        if price:
            price = float(price)
        if fdv:
            fdv = float(fdv)
        
        top_pairs.append(TopPair(
            pair=pair.get("pairAddress", "unknown"),
            price_usd=price or 0.0,
            liquidity_usd=liq,
            volume_24h_usd=vol,
            fdv_usd=fdv
        ))
        
        total_liquidity += liq
    
    # Calculate flags
    flags = []
    
    # Low liquidity flag
    if total_liquidity < 100_000:
        flags.append(LiquidityFlag(
            type="dex_liquidity_low",
            severity="high",
            reason=f"Total liquidity ${total_liquidity:,.0f} below $100K threshold"
        ))
    elif total_liquidity < 500_000:
        flags.append(LiquidityFlag(
            type="dex_liquidity_low",
            severity="medium",
            reason=f"Total liquidity ${total_liquidity:,.0f} below $500K threshold"
        ))
    
    # Concentration flag
    if sorted_pairs and total_liquidity > 0:
        top_pool_share = sorted_pairs[0].get("liquidity", {}).get("usd", 0) / total_liquidity
        if top_pool_share > 0.7:
            flags.append(LiquidityFlag(
                type="liquidity_concentrated",
                severity="high",
                reason=f"Top pool accounts for {top_pool_share*100:.0f}% of liquidity"
            ))
        elif top_pool_share > 0.5:
            flags.append(LiquidityFlag(
                type="liquidity_concentrated",
                severity="medium",
                reason=f"Top pool accounts for {top_pool_share*100:.0f}% of liquidity"
            ))
    
    return DEXData(
        provider=dex_req.provider,
        chainId=dex_req.chain_id,
        pairs_found=len(pairs),
        top_pairs=top_pairs,
        flags=flags
    ), errors


async def _analyze_cex_venue(cex_req) -> CEXData:
    """
    Analyze CEX orderbook (placeholder - not fully implemented).
    Returns nulls + flags for unsupported venues.
    """
    # CEX integration not fully implemented - return placeholder
    return CEXData(
        venue=cex_req.venue,
        symbol=cex_req.symbol,
        mid_price=None,
        spread_bps=None,
        depth=CEXDepth(
            within_10bps_usd=None,
            within_25bps_usd=None,
            within_50bps_usd=None
        ),
        impact_estimates=[],
        flags=[LiquidityFlag(
            type="thin_depth",
            severity="high",
            reason=f"CEX venue '{cex_req.venue}' not yet implemented"
        )]
    )


def _calculate_liquidity_score(
    total_liquidity: float,
    total_volume: float,
    dex_data_list: List[DEXData],
    cex_data_list: List[CEXData]
) -> LiquidityScore:
    """
    Calculate deterministic liquidity score (0-1).
    Based on: liquidity level, volume/liquidity ratio, concentration penalty.
    """
    score = 0.0
    
    # Base score from liquidity level
    if total_liquidity >= 10_000_000:
        score += 0.5
    elif total_liquidity >= 1_000_000:
        score += 0.35
    elif total_liquidity >= 500_000:
        score += 0.25
    elif total_liquidity >= 100_000:
        score += 0.15
    else:
        score += 0.05
    
    # Volume/liquidity ratio (healthy = 0.5-2.0)
    if total_liquidity > 0:
        vol_liq_ratio = total_volume / total_liquidity
        if 0.5 <= vol_liq_ratio <= 2.0:
            score += 0.2
        elif 0.2 <= vol_liq_ratio <= 5.0:
            score += 0.1
    
    # Concentration penalty
    concentration_flags = sum(
        1 for d in dex_data_list 
        for f in d.flags 
        if f.type == "liquidity_concentrated" and f.severity == "high"
    )
    if concentration_flags == 0:
        score += 0.15
    elif concentration_flags == 1:
        score += 0.05
    
    # CEX depth bonus (if available)
    has_cex_depth = any(c.depth.within_10bps_usd is not None for c in cex_data_list)
    if has_cex_depth:
        score += 0.15
    
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    
    # Label
    if score >= 0.7:
        label = "high"
    elif score >= 0.4:
        label = "medium"
    else:
        label = "low"
    
    return LiquidityScore(score=score, label=label)
