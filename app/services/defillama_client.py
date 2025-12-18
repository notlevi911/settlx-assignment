"""
DefiLlama API client for CEX volume and historical data.
"""
import httpx
from typing import Optional, Dict, Any, List, Tuple
from app.api.v1.schemas.responses import StructuredError, ErrorCode


class DefiLlamaClient:
    """Client for DefiLlama API."""
    
    def __init__(self):
        self.base_url = "https://api.llama.fi"
        self.coins_url = "https://coins.llama.fi"
        self.timeout = 15.0
    
    async def get_token_price(self, chain: str, address: str) -> Tuple[Optional[float], Optional[StructuredError]]:
        """Get current token price."""
        try:
            # DefiLlama format: chain:address
            coin_id = f"{chain}:{address}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.coins_url}/prices/current/{coin_id}"
                )
                response.raise_for_status()
                data = response.json()
                
                if "coins" in data and coin_id in data["coins"]:
                    price = data["coins"][coin_id].get("price")
                    return price, None
                
                return None, StructuredError(
                    code=ErrorCode.UPSTREAM_ERROR,
                    message=f"Token {coin_id} not found in DefiLlama",
                    source="defillama",
                    retryable=False
                )
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="DefiLlama API timed out",
                source="defillama",
                retryable=True
            )
        except httpx.HTTPError as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"DefiLlama HTTP error: {str(e)}",
                source="defillama",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"DefiLlama error: {str(e)}",
                source="defillama",
                retryable=False
            )
    
    async def get_protocol_tvl(self, protocol_slug: str) -> Tuple[Optional[Dict], Optional[StructuredError]]:
        """Get protocol TVL and chain breakdown."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/protocol/{protocol_slug}"
                )
                response.raise_for_status()
                data = response.json()
                
                return data, None
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="DefiLlama API timed out",
                source="defillama",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"DefiLlama error: {str(e)}",
                source="defillama",
                retryable=False
            )
    
    async def get_historical_tvl(
        self,
        chain: str,
        address: str,
        days_back: int = 30
    ) -> Tuple[Optional[List[Dict]], Optional[StructuredError]]:
        """
        Get historical TVL/liquidity data.
        Note: DefiLlama doesn't provide per-token historical data easily.
        This is a placeholder for protocol-level data.
        """
        try:
            coin_id = f"{chain}:{address}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Historical prices endpoint
                response = await client.get(
                    f"{self.coins_url}/chart/{coin_id}",
                    params={"span": days_back}
                )
                response.raise_for_status()
                data = response.json()
                
                if "coins" in data and coin_id in data["coins"]:
                    prices = data["coins"][coin_id].get("prices", [])
                    return prices, None
                
                return None, StructuredError(
                    code=ErrorCode.UPSTREAM_ERROR,
                    message="Historical data not available",
                    source="defillama",
                    retryable=False
                )
                
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"Historical data error: {str(e)}",
                source="defillama",
                retryable=False
            )
    
    async def get_stablecoins(self) -> Tuple[Optional[List[Dict]], Optional[StructuredError]]:
        """Get stablecoin data (useful for reference)."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/stablecoins")
                response.raise_for_status()
                data = response.json()
                
                return data.get("peggedAssets", []), None
                
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"Stablecoins fetch error: {str(e)}",
                source="defillama",
                retryable=False
            )


class CEXIntegration:
    """
    CEX orderbook depth integration.
    Would integrate with Binance/Coinbase/etc APIs.
    Placeholder implementation.
    """
    
    def __init__(self):
        self.supported_venues = ["binance", "coinbase", "kraken", "okx"]
    
    async def get_orderbook_depth(
        self,
        venue: str,
        symbol: str,
        depth_levels: List[int]
    ) -> Tuple[Optional[Dict], Optional[StructuredError]]:
        """
        Get CEX orderbook depth.
        
        Returns:
            {
                "bid_depth_usd": {...},  # depth at each level
                "ask_depth_usd": {...},
                "spread_bps": float,
                "mid_price": float
            }
        """
        if venue.lower() not in self.supported_venues:
            return None, StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=f"CEX venue '{venue}' not yet supported",
                source=venue,
                retryable=False
            )
        
        # Placeholder: Would implement actual API calls
        # For Binance: GET /api/v3/depth?symbol=BTCUSDT&limit=5000
        # Then calculate depth at each BPS level
        
        return None, StructuredError(
            code=ErrorCode.UNSUPPORTED_SOURCE,
            message=f"CEX integration for {venue} not yet implemented",
            source=venue,
            retryable=False
        )
