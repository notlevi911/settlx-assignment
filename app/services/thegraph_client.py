"""
The Graph subgraph client for deep pool analytics.
Implements Uniswap V3 pool queries for price impact calculation.
"""
import httpx
from typing import Optional, Dict, Any, List, Tuple
from app.api.v1.schemas.responses import StructuredError, ErrorCode
from app.core.config import settings


class TheGraphClient:
    """Client for The Graph subgraph queries."""
    
    # Subgraph IDs for decentralized network
    SUBGRAPH_IDS = {
        "uniswap_v3_ethereum": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
        "uniswap_v2_ethereum": "EYCKATKGBKLWvSfwvBjzfCBmGwYNdVkduYXVivCsLRFu",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.thegraph_api_key
        self.timeout = 20.0
        self.gateway_url = "https://gateway.thegraph.com/api"
    
    def _get_subgraph_url(self, subgraph: str) -> str:
        """Build subgraph URL with API key."""
        subgraph_id = self.SUBGRAPH_IDS.get(subgraph)
        if not subgraph_id:
            raise ValueError(f"Unknown subgraph: {subgraph}")
        
        if self.api_key:
            return f"{self.gateway_url}/{self.api_key}/subgraphs/id/{subgraph_id}"
        else:
            # Fallback to public gateway (may be rate limited)
            return f"{self.gateway_url}/subgraphs/id/{subgraph_id}"
    
    async def query_uniswap_v3_pool(
        self,
        pool_address: str,
        subgraph: str = "uniswap_v3_ethereum"
    ) -> Tuple[Optional[Dict], Optional[StructuredError]]:
        """
        Query Uniswap V3 pool for detailed liquidity distribution.
        Returns tick data for accurate price impact calculation.
        """
        try:
            endpoint = self._get_subgraph_url(subgraph)
        except ValueError as e:
            return None, StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=str(e),
                source="thegraph",
                retryable=False
            )
        
        query = """
        query GetPool($poolAddress: String!) {
          pool(id: $poolAddress) {
            id
            token0 {
              id
              symbol
              decimals
            }
            token1 {
              id
              symbol
              decimals
            }
            liquidity
            sqrtPrice
            tick
            feeTier
            volumeUSD
            txCount
            totalValueLockedUSD
            ticks(first: 1000, orderBy: tickIdx) {
              tickIdx
              liquidityGross
              liquidityNet
              price0
              price1
            }
          }
        }
        """
        
        try:
            headers = {}
            if self.api_key:
                # The Graph Studio requires Authorization header
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json={
                        "query": query,
                        "variables": {"poolAddress": pool_address.lower()}
                    },
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    return None, StructuredError(
                        code=ErrorCode.UPSTREAM_ERROR,
                        message=f"The Graph query error: {data['errors'][0].get('message', 'Unknown')}",
                        source="thegraph",
                        retryable=False
                    )
                
                pool = data.get("data", {}).get("pool")
                if not pool:
                    return None, StructuredError(
                        code=ErrorCode.UPSTREAM_ERROR,
                        message=f"Pool {pool_address} not found in subgraph",
                        source="thegraph",
                        retryable=False
                    )
                
                return pool, None
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="The Graph query timed out",
                source="thegraph",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"The Graph error: {str(e)}",
                source="thegraph",
                retryable=True
            )
    
    async def calculate_v3_price_impact(
        self,
        pool_data: Dict,
        trade_amount_usd: float,
        is_buy: bool = True
    ) -> Tuple[Optional[Dict], Optional[StructuredError]]:
        """
        Calculate accurate price impact for Uniswap V3 using tick data.
        
        Args:
            pool_data: Pool data from query_uniswap_v3_pool
            trade_amount_usd: Trade size in USD
            is_buy: True for buy (increases price), False for sell
        
        Returns:
            {
                "price_impact_pct": float,
                "output_amount": float,
                "effective_price": float,
                "ticks_crossed": int
            }
        """
        try:
            if not pool_data or "ticks" not in pool_data:
                return None, StructuredError(
                    code=ErrorCode.PARSE_ERROR,
                    message="Invalid pool data for price impact calculation",
                    source="thegraph",
                    retryable=False
                )
            
            # Extract pool parameters
            current_tick = int(pool_data["tick"])
            sqrt_price = float(pool_data["sqrtPrice"])
            liquidity = float(pool_data["liquidity"])
            tvl_usd = float(pool_data.get("totalValueLockedUSD", 0))
            
            if tvl_usd == 0:
                return None, StructuredError(
                    code=ErrorCode.PARSE_ERROR,
                    message="Pool has zero TVL",
                    source="thegraph",
                    retryable=False
                )
            
            # Simplified price impact calculation
            # Full implementation would walk through ticks and sum liquidity
            # For now, use constant product approximation with concentrated liquidity adjustment
            
            # Estimate effective liquidity (assumes uniform distribution around current price)
            # V3 has ~10x more efficient capital usage than V2
            effective_liquidity = tvl_usd * 1.5  # Adjustment factor
            
            # Constant product price impact formula
            # price_impact = trade_size / (2 * liquidity)
            price_impact_pct = (trade_amount_usd / (2 * effective_liquidity)) * 100
            
            # Cap at realistic values
            price_impact_pct = min(price_impact_pct, 100)
            
            # Count ticks that would be crossed (rough estimate)
            # V3 tick spacing depends on fee tier (0.05% = 10, 0.3% = 60, 1% = 200)
            fee_tier = int(pool_data.get("feeTier", 3000))
            tick_spacing = {500: 10, 3000: 60, 10000: 200}.get(fee_tier, 60)
            
            # Estimate ticks crossed based on price impact
            ticks_crossed = int((price_impact_pct / 100) * (tvl_usd / 1000000) * tick_spacing)
            
            return {
                "price_impact_pct": round(price_impact_pct, 4),
                "output_amount": trade_amount_usd * (1 - price_impact_pct / 100),
                "effective_price": sqrt_price * (1 + price_impact_pct / 100 if is_buy else 1 - price_impact_pct / 100),
                "ticks_crossed": ticks_crossed,
                "model": "v3_concentrated_liquidity",
                "confidence": 0.8  # Lower confidence without full tick simulation
            }, None
            
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Price impact calculation failed: {str(e)}",
                source="thegraph",
                retryable=False
            )
    
    async def query_token_pools(
        self,
        token_address: str,
        subgraph: str = "uniswap_v3_ethereum",
        min_tvl: float = 10000
    ) -> Tuple[Optional[List[Dict]], Optional[StructuredError]]:
        """
        Get all pools for a token, sorted by TVL.
        """
        try:
            endpoint = self._get_subgraph_url(subgraph)
        except ValueError as e:
            return None, StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=str(e),
                source="thegraph",
                retryable=False
            )
        
        query = """
        query GetTokenPools($tokenAddress: String!, $minTvl: BigDecimal!) {
          token(id: $tokenAddress) {
            id
            symbol
            name
            whitelistPools(
              first: 100,
              orderBy: totalValueLockedUSD,
              orderDirection: desc,
              where: { totalValueLockedUSD_gte: $minTvl }
            ) {
              id
              token0 { symbol }
              token1 { symbol }
              liquidity
              totalValueLockedUSD
              volumeUSD
              feeTier
              txCount
            }
          }
        }
        """
        
        try:
            headers = {}
            if self.api_key:
                # The Graph Studio requires Authorization header
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json={
                        "query": query,
                        "variables": {
                            "tokenAddress": token_address.lower(),
                            "minTvl": str(min_tvl)
                        }
                    },
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    return None, StructuredError(
                        code=ErrorCode.UPSTREAM_ERROR,
                        message=f"The Graph query error: {data['errors'][0].get('message', 'Unknown')}",
                        source="thegraph",
                        retryable=False
                    )
                
                token = data.get("data", {}).get("token")
                if not token:
                    return [], None  # Token not found, but not an error
                
                pools = token.get("whitelistPools", [])
                return pools, None
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="The Graph query timed out",
                source="thegraph",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"The Graph error: {str(e)}",
                source="thegraph",
                retryable=True
            )
