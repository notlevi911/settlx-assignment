"""
Solana RPC client for SPL token analysis.
Uses Helius or any Solana RPC provider.
"""
import httpx
from typing import Optional, Dict, Any, Tuple
from app.core.config import settings
from app.api.v1.schemas.responses import StructuredError, ErrorCode
import base64
import base58
import struct


class SolanaClient:
    """Client for Solana RPC and SPL token analysis."""
    
    def __init__(self):
        self.rpc_url = settings.solana_rpc_url or "https://api.mainnet-beta.solana.com"
        self.timeout = 15.0
    
    async def get_token_supply(self, mint_address: str) -> Tuple[Optional[float], Optional[StructuredError]]:
        """Get SPL token supply."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTokenSupply",
                        "params": [mint_address]
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    return None, StructuredError(
                        code=ErrorCode.UPSTREAM_ERROR,
                        message=f"Solana RPC error: {data['error'].get('message', 'Unknown')}",
                        source="solana_rpc",
                        retryable=False
                    )
                
                result = data.get("result", {})
                supply = result.get("value", {})
                ui_amount = supply.get("uiAmount")
                
                return ui_amount, None
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="Solana RPC request timed out",
                source="solana_rpc",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"Failed to fetch token supply: {str(e)}",
                source="solana_rpc",
                retryable=True
            )
    
    async def get_account_info(self, address: str) -> Tuple[Optional[Dict[str, Any]], Optional[StructuredError]]:
        """Get account info including program data."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getAccountInfo",
                        "params": [
                            address,
                            {"encoding": "base64"}
                        ]
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    return None, StructuredError(
                        code=ErrorCode.UPSTREAM_ERROR,
                        message=f"Solana RPC error: {data['error'].get('message', 'Unknown')}",
                        source="solana_rpc",
                        retryable=False
                    )
                
                result = data.get("result", {})
                return result.get("value"), None
                
        except httpx.TimeoutException:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_TIMEOUT,
                message="Solana RPC request timed out",
                source="solana_rpc",
                retryable=True
            )
        except Exception as e:
            return None, StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"Failed to fetch account info: {str(e)}",
                source="solana_rpc",
                retryable=True
            )
    
    async def analyze_spl_token(self, mint_address: str) -> Dict[str, Any]:
        """
        Analyze SPL token mint account.
        Returns mint authority, freeze authority, decimals, supply.
        """
        account_info, error = await self.get_account_info(mint_address)
        
        if error:
            return {
                "is_verified": None,
                "mint_authority": None,
                "freeze_authority": None,
                "decimals": None,
                "supply": None,
                "is_initialized": None,
                "error": error
            }
        
        if not account_info:
            return {
                "is_verified": False,
                "mint_authority": None,
                "freeze_authority": None,
                "decimals": None,
                "supply": None,
                "is_initialized": False,
                "error": StructuredError(
                    code=ErrorCode.INVALID_ADDRESS,
                    message="Account not found on Solana",
                    source="solana_rpc",
                    retryable=False
                )
            }
        
        try:
            # Parse SPL Token Mint account structure
            # Reference: https://docs.rs/spl-token/latest/spl_token/state/struct.Mint.html
            data_b64 = account_info.get("data", [""])[0]
            data = base64.b64decode(data_b64)
            
            if len(data) < 82:  # Minimum size for Mint account
                return {
                    "is_verified": False,
                    "error": StructuredError(
                        code=ErrorCode.PARSE_ERROR,
                        message="Invalid SPL token mint data",
                        source="solana_rpc",
                        retryable=False
                    )
                }
            
            # Parse Mint structure:
            # 0-4: mint_authority_option (0 or 1)
            # 4-36: mint_authority (pubkey)
            # 36-44: supply (u64)
            # 44: decimals (u8)
            # 45: is_initialized (bool)
            # 46-50: freeze_authority_option (0 or 1)
            # 50-82: freeze_authority (pubkey)
            
            mint_auth_option = struct.unpack('<I', data[0:4])[0]
            mint_authority = None
            if mint_auth_option == 1:
                mint_authority = base58.b58encode(data[4:36]).decode('utf-8')
            
            supply_raw = struct.unpack('<Q', data[36:44])[0]
            decimals = data[44]
            is_initialized = data[45] == 1
            
            freeze_auth_option = struct.unpack('<I', data[46:50])[0]
            freeze_authority = None
            if freeze_auth_option == 1:
                freeze_authority = base58.b58encode(data[50:82]).decode('utf-8')
            
            supply = supply_raw / (10 ** decimals) if decimals else supply_raw
            
            return {
                "is_verified": True,  # Successfully parsed
                "mint_authority": mint_authority,
                "freeze_authority": freeze_authority,
                "decimals": decimals,
                "supply": supply,
                "is_initialized": is_initialized,
                "authority_renounced": mint_authority is None,
                "freeze_disabled": freeze_authority is None,
                "error": None
            }
            
        except Exception as e:
            return {
                "is_verified": False,
                "error": StructuredError(
                    code=ErrorCode.PARSE_ERROR,
                    message=f"Failed to parse SPL token data: {str(e)}",
                    source="solana_rpc",
                    retryable=False
                )
            }
    
    async def check_program_upgradeable(self, program_id: str) -> Tuple[Optional[bool], Optional[str], Optional[StructuredError]]:
        """
        Check if a Solana program is upgradeable.
        Returns: (is_upgradeable, upgrade_authority, error)
        """
        account_info, error = await self.get_account_info(program_id)
        
        if error:
            return None, None, error
        
        if not account_info:
            return None, None, StructuredError(
                code=ErrorCode.INVALID_ADDRESS,
                message="Program account not found",
                source="solana_rpc",
                retryable=False
            )
        
        # Check if account is owned by BPF Loader Upgradeable
        owner = account_info.get("owner", "")
        if owner == "BPFLoaderUpgradeab1e11111111111111111111111":
            # This is an upgradeable program
            # Would need to query ProgramData account for upgrade authority
            # For now, return True (upgradeable)
            return True, None, None
        elif owner == "BPFLoader2111111111111111111111111111111111":
            # Non-upgradeable
            return False, None, None
        else:
            return None, None, StructuredError(
                code=ErrorCode.PARSE_ERROR,
                message=f"Unknown program loader: {owner}",
                source="solana_rpc",
                retryable=False
            )
