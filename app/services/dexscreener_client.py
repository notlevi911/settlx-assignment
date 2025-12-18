"""
DexScreener API client.
Fetches DEX liquidity, volume, and pair data.
"""
import httpx
from typing import Dict, List, Optional, Any
from app.core.config import settings


class DexScreenerClient:
    """Client for DexScreener DEX aggregation API."""
    
    def __init__(self):
        self.base_url = settings.dexscreener_base_url
    
    async def get_token_pairs(self, chain: str, address: str) -> Dict[str, Any]:
        """
        Fetch all DEX pairs for a token.
        
        Returns:
            {pairs: [...], error: None} or {pairs: [], error: str}
        """
        # DexScreener chain mapping
        chain_map = {
            "ethereum": "ethereum",
            "bsc": "bsc",
            "polygon": "polygon",
            "arbitrum": "arbitrum",
            "optimism": "optimism",
            "avalanche": "avalanche"
        }
        
        chain_id = chain_map.get(chain.lower())
        if not chain_id:
            return {
                "pairs": [],
                "error": f"Unsupported chain: {chain}"
            }
        
        try:
            url = f"{self.base_url}/dex/tokens/{address}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                # Filter pairs by chain
                all_pairs = data.get("pairs", [])
                chain_pairs = [
                    pair for pair in all_pairs
                    if pair.get("chainId", "").lower() == chain_id.lower()
                ]
                
                return {
                    "pairs": chain_pairs,
                    "error": None
                }
        
        except httpx.HTTPError as e:
            return {
                "pairs": [],
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "pairs": [],
                "error": f"Error fetching pairs: {str(e)}"
            }
    
    def calculate_liquidity_stats(self, pairs: List[Dict]) -> Dict[str, Any]:
        """
        Calculate aggregate liquidity statistics from pairs.
        
        Returns:
            {
                total_liquidity_usd: float,
                top_pool_liquidity_usd: float,
                pool_count: int,
                liquidity_distribution: {pool_name: usd},
                top_pool_percentage: float
            }
        """
        if not pairs:
            return {
                "total_liquidity_usd": None,
                "top_pool_liquidity_usd": None,
                "pool_count": 0,
                "liquidity_distribution": {},
                "top_pool_percentage": None
            }
        
        # Extract liquidity per pool
        pool_liquidity = {}
        for pair in pairs:
            pool_name = f"{pair.get('dexId', 'unknown')}:{pair.get('pairAddress', '')[:8]}"
            liquidity_usd = pair.get("liquidity", {}).get("usd", 0)
            pool_liquidity[pool_name] = liquidity_usd
        
        total_liquidity = sum(pool_liquidity.values())
        top_pool_liquidity = max(pool_liquidity.values()) if pool_liquidity else 0
        top_pool_percentage = (top_pool_liquidity / total_liquidity * 100) if total_liquidity > 0 else 0
        
        return {
            "total_liquidity_usd": total_liquidity,
            "top_pool_liquidity_usd": top_pool_liquidity,
            "pool_count": len(pairs),
            "liquidity_distribution": pool_liquidity,
            "top_pool_percentage": round(top_pool_percentage, 2)
        }
    
    def calculate_volume_stats(self, pairs: List[Dict]) -> Dict[str, Any]:
        """
        Calculate aggregate volume statistics.
        
        Returns:
            {
                volume_24h_usd: float,
                volume_to_liquidity_ratio: float
            }
        """
        if not pairs:
            return {
                "volume_24h_usd": None,
                "volume_to_liquidity_ratio": None
            }
        
        total_volume_24h = sum(pair.get("volume", {}).get("h24", 0) for pair in pairs)
        total_liquidity = sum(pair.get("liquidity", {}).get("usd", 0) for pair in pairs)
        
        volume_to_liquidity = (total_volume_24h / total_liquidity) if total_liquidity > 0 else 0
        
        return {
            "volume_24h_usd": total_volume_24h,
            "volume_to_liquidity_ratio": round(volume_to_liquidity, 3)
        }
    
    def estimate_slippage(self, liquidity_usd: float, trade_size_usd: float) -> float:
        """
        Estimate slippage % for a given trade size.
        
        Simplified model: slippage ~= (trade_size / liquidity) * constant
        This is a rough heuristic, real slippage depends on AMM curve.
        
        Returns:
            Estimated slippage as percentage (e.g., 2.5 = 2.5%)
        """
        if liquidity_usd <= 0:
            return 100.0  # No liquidity = infinite slippage
        
        # Constant product AMM approximation
        # For x*y=k, slippage ≈ Δx / (x + Δx/2)
        # Simplified to: slippage ≈ (trade_size / liquidity) * amplification_factor
        amplification_factor = 1.5  # Heuristic adjustment
        
        raw_slippage = (trade_size_usd / liquidity_usd) * amplification_factor * 100
        
        return min(100.0, round(raw_slippage, 2))
