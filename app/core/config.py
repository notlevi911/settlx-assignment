"""
Configuration management using Pydantic settings.
Loads from environment variables with validation.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # API Keys
    etherscan_api_key: str = ""
    bscscan_api_key: str = ""
    polygonscan_api_key: str = ""
    cryptopanic_api_key: str = ""
    thegraph_api_key: str = ""
    
    # RPC Endpoints
    ethereum_rpc_url: str = "https://eth.llamarpc.com"
    bsc_rpc_url: str = "https://bsc-dataseed.binance.org/"
    polygon_rpc_url: str = "https://polygon-rpc.com/"
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"  # Can use Helius for production
    
    # Service URLs
    dexscreener_base_url: str = "https://api.dexscreener.com/latest"
    defillama_base_url: str = "https://api.llama.fi"
    thegraph_base_url: str = "https://api.thegraph.com/subgraphs/name"
    cryptopanic_base_url: str = "https://cryptopanic.com/api/developer/v2"
    
    # Cache settings
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 300
    
    # App settings
    app_name: str = "Token Due Diligence Engine"
    app_version: str = "1.0.0"
    debug: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    def get_explorer_api_key(self, chain: str) -> str:
        """Get the appropriate block explorer API key for a chain."""
        mapping = {
            "ethereum": self.etherscan_api_key,
            "bsc": self.bscscan_api_key,
            "polygon": self.polygonscan_api_key,
        }
        return mapping.get(chain.lower(), "")
    
    def get_rpc_url(self, chain: str) -> str:
        """Get RPC endpoint for a chain."""
        mapping = {
            "ethereum": self.ethereum_rpc_url,
            "bsc": self.bsc_rpc_url,
            "polygon": self.polygon_rpc_url,
            "solana": self.solana_rpc_url,
        }
        return mapping.get(chain.lower(), "")


settings = Settings()
