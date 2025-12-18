"""
Block explorer API client.
Fetches contract source code and verification status.
"""
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings


class ExplorerClient:
    """Client for blockchain explorer APIs (Etherscan-like)."""
    
    EXPLORER_URLS = {
        "ethereum": "https://api.etherscan.io/v2/api",
        "bsc": "https://api.bscscan.com/v2/api",
        "polygon": "https://api.polygonscan.com/v2/api",
        "arbitrum": "https://api.arbiscan.io/v2/api",
        "optimism": "https://api-optimistic.etherscan.io/v2/api",
        "avalanche": "https://api.snowtrace.io/v2/api",
    }
    
    CHAIN_IDS = {
        "ethereum": "1",
        "bsc": "56",
        "polygon": "137",
        "arbitrum": "42161",
        "optimism": "10",
        "avalanche": "43114",
    }
    
    def __init__(self, chain: str):
        self.chain = chain.lower()
        self.base_url = self.EXPLORER_URLS.get(self.chain)
        self.chain_id = self.CHAIN_IDS.get(self.chain)
        self.api_key = settings.get_explorer_api_key(self.chain)
        
        if not self.base_url:
            raise ValueError(f"Unsupported chain: {chain}")
    
    async def get_contract_source(self, address: str) -> Dict[str, Any]:
        """
        Fetch contract source code and verification status.
        Returns dict with: {verified, source_code, abi, compiler_version, ...}
        """
        if not self.api_key:
            return {
                "verified": False,
                "source_code": None,
                "error": f"No API key configured for {self.chain}"
            }
        
        params = {
            "chainid": self.chain_id,
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "1" or not data.get("result"):
                    return {
                        "verified": False,
                        "source_code": None,
                        "error": "Contract not verified or not found"
                    }
                
                result = data["result"][0]
                source_code = result.get("SourceCode", "")
                
                return {
                    "verified": bool(source_code),
                    "source_code": source_code if source_code else None,
                    "abi": result.get("ABI"),
                    "compiler_version": result.get("CompilerVersion"),
                    "optimization_used": result.get("OptimizationUsed") == "1",
                    "contract_name": result.get("ContractName"),
                    "constructor_arguments": result.get("ConstructorArguments"),
                }
        
        except httpx.HTTPError as e:
            return {
                "verified": False,
                "source_code": None,
                "error": f"HTTP error fetching source: {str(e)}"
            }
        except Exception as e:
            return {
                "verified": False,
                "source_code": None,
                "error": f"Error fetching source: {str(e)}"
            }
    
    async def get_contract_abi(self, address: str) -> Optional[str]:
        """Fetch contract ABI if verified."""
        source_data = await self.get_contract_source(address)
        return source_data.get("abi")
    
    async def get_transaction_count(self, address: str) -> Optional[int]:
        """Get number of transactions for an address."""
        params = {
            "chainid": self.chain_id,
            "module": "proxy",
            "action": "eth_getTransactionCount",
            "address": address,
            "tag": "latest",
            "apikey": self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get("result"):
                    return int(data["result"], 16)
                return None
        
        except Exception:
            return None
