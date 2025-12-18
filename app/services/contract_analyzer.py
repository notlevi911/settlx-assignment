"""
Contract analysis utilities.
Detects proxy patterns, admin functions, and ownership structures.
"""
from typing import Optional, Dict, List, Tuple
from web3 import Web3
from eth_utils import is_address, to_checksum_address
import re


class ContractAnalyzer:
    """Analyzes smart contract bytecode and source code for risk patterns."""
    
    # Known proxy patterns
    PROXY_PATTERNS = {
        "EIP-1967": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",  # implementation slot
        "EIP-1822": "0xc5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7",  # proxiable slot
        "EIP-897": "implementation()",
    }
    
    # Function signatures that indicate admin powers
    ADMIN_FUNCTION_SIGS = {
        "mint": ["mint(address,uint256)", "mint(uint256)"],
        "burn": ["burn(address,uint256)", "burn(uint256)", "burnFrom(address,uint256)"],
        "pause": ["pause()", "pause(bool)"],
        "unpause": ["unpause()"],
        "freeze": ["freeze(address)", "freezeAccount(address,bool)"],
        "setOwner": ["transferOwnership(address)", "setOwner(address)"],
        "upgrade": ["upgradeTo(address)", "upgradeToAndCall(address,bytes)"],
    }
    
    def __init__(self, web3: Web3):
        self.web3 = web3
    
    def detect_proxy(self, address: str) -> Tuple[bool, Optional[str], str]:
        """
        Detect if address is a proxy and find implementation.
        Returns: (is_proxy, implementation_address, evidence)
        """
        if not is_address(address):
            return False, None, "Invalid address"
        
        address = to_checksum_address(address)
        
        # Check EIP-1967 implementation slot
        try:
            impl_slot = self.PROXY_PATTERNS["EIP-1967"]
            storage = self.web3.eth.get_storage_at(address, int(impl_slot, 16))
            impl_address = self.web3.to_checksum_address("0x" + storage.hex()[-40:])
            
            if impl_address != "0x0000000000000000000000000000000000000000":
                return True, impl_address, f"EIP-1967 proxy, implementation at slot {impl_slot}"
        except Exception:
            pass
        
        # Check EIP-1822 proxiable slot
        try:
            proxiable_slot = self.PROXY_PATTERNS["EIP-1822"]
            storage = self.web3.eth.get_storage_at(address, int(proxiable_slot, 16))
            impl_address = self.web3.to_checksum_address("0x" + storage.hex()[-40:])
            
            if impl_address != "0x0000000000000000000000000000000000000000":
                return True, impl_address, f"EIP-1822 UUPS proxy, implementation at slot {proxiable_slot}"
        except Exception:
            pass
        
        # Check for implementation() function (EIP-897)
        try:
            impl_sig = self.web3.keccak(text="implementation()")[:4].hex()
            result = self.web3.eth.call({"to": address, "data": impl_sig})
            if len(result) == 32:
                impl_address = self.web3.to_checksum_address("0x" + result.hex()[-40:])
                if impl_address != "0x0000000000000000000000000000000000000000":
                    return True, impl_address, "EIP-897 proxy with implementation() function"
        except Exception:
            pass
        
        return False, None, "No proxy pattern detected"
    
    def check_upgradeability(self, address: str, is_proxy: bool) -> Tuple[bool, str]:
        """
        Determine if contract is upgradeable.
        Returns: (is_upgradeable, evidence)
        """
        if not is_proxy:
            return False, "Not a proxy contract"
        
        # Check for common upgrade functions
        upgrade_functions = ["upgradeTo", "upgradeToAndCall", "setImplementation"]
        
        for func_name in upgrade_functions:
            try:
                # Try multiple common signatures
                for sig in [f"{func_name}(address)", f"{func_name}(address,bytes)"]:
                    func_sig = self.web3.keccak(text=sig)[:4].hex()
                    # Try to call (will fail if function exists but we have no permission, but won't throw if function doesn't exist)
                    try:
                        self.web3.eth.call({"to": address, "data": func_sig + "0" * 64})
                    except Exception as e:
                        # If we get an execution error (not "function not found"), function likely exists
                        if "execution reverted" in str(e).lower() or "invalid opcode" in str(e).lower():
                            return True, f"Upgradeable: {sig} function detected"
            except Exception:
                continue
        
        # If proxy but no upgrade function found, likely immutable proxy
        return False, "Proxy detected but no upgrade function found (possibly immutable)"
    
    def detect_admin_functions(self, source_code: Optional[str]) -> Dict[str, Tuple[bool, str]]:
        """
        Scan source code for admin functions.
        Returns: {function_type: (exists, evidence)}
        """
        results = {}
        
        if not source_code:
            return {
                "mint": (False, "Source code not available"),
                "burn": (False, "Source code not available"),
                "pause": (False, "Source code not available"),
                "freeze": (False, "Source code not available"),
            }
        
        # Search for mint functions
        mint_patterns = [r'\bfunction\s+mint\s*\(', r'\bfunction\s+_mint\s*\(']
        has_mint = any(re.search(pattern, source_code, re.IGNORECASE) for pattern in mint_patterns)
        results["mint"] = (has_mint, "mint() function found in source" if has_mint else "No mint function detected")
        
        # Search for burn functions
        burn_patterns = [r'\bfunction\s+burn\s*\(', r'\bfunction\s+_burn\s*\(', r'\bfunction\s+burnFrom\s*\(']
        has_burn = any(re.search(pattern, source_code, re.IGNORECASE) for pattern in burn_patterns)
        results["burn"] = (has_burn, "burn() function found in source" if has_burn else "No burn function detected")
        
        # Search for pause functions
        pause_patterns = [r'\bfunction\s+pause\s*\(', r'\bwhenNotPaused\b']
        has_pause = any(re.search(pattern, source_code, re.IGNORECASE) for pattern in pause_patterns)
        results["pause"] = (has_pause, "pause mechanism found in source" if has_pause else "No pause mechanism detected")
        
        # Search for freeze/blacklist functions
        freeze_patterns = [r'\bfunction\s+freeze\s*\(', r'\bfunction\s+blacklist\s*\(', r'\bfreeze.*Account\b']
        has_freeze = any(re.search(pattern, source_code, re.IGNORECASE) for pattern in freeze_patterns)
        results["freeze"] = (has_freeze, "freeze/blacklist function found in source" if has_freeze else "No freeze mechanism detected")
        
        return results
    
    def detect_ownership(self, source_code: Optional[str], address: str) -> Tuple[Optional[str], bool, str]:
        """
        Detect owner and if ownership is renounced.
        Returns: (owner_address, is_renounced, evidence)
        """
        if not source_code:
            return None, False, "Source code not available for ownership analysis"
        
        # Check for Ownable pattern
        has_ownable = "contract Ownable" in source_code or "is Ownable" in source_code
        
        if not has_ownable:
            return None, True, "No Ownable pattern detected (likely no centralized owner)"
        
        # Try to read owner from contract
        try:
            owner_sig = self.web3.keccak(text="owner()")[:4].hex()
            result = self.web3.eth.call({"to": address, "data": owner_sig})
            owner_address = self.web3.to_checksum_address("0x" + result.hex()[-40:])
            
            # Check if owner is zero address (renounced)
            if owner_address == "0x0000000000000000000000000000000000000000":
                return None, True, "Ownership renounced (owner is zero address)"
            
            return owner_address, False, f"Owner address: {owner_address}"
        
        except Exception as e:
            return None, False, f"Ownable pattern found but owner() call failed: {str(e)}"
