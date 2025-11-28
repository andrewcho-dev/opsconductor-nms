"""
Base class for vendor-specific discovery implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from ..types import SystemInfo, RouteEntry


class VendorDiscoveryBase(ABC):
    """Abstract base class for vendor-specific network discovery."""
    
    def __init__(self, timeout: int = 10, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
    
    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Return the vendor name this class handles."""
        pass
    
    @property
    @abstractmethod
    def supported_patterns(self) -> List[str]:
        """Return list of patterns that identify this vendor."""
        pass
    
    @abstractmethod
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Determine if this vendor matches the given system info."""
        pass
    
    @abstractmethod
    def get_ssh_commands(self) -> List[str]:
        """Return list of SSH commands to try for this vendor."""
        pass
    
    @abstractmethod
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse routing table output from this vendor."""
        pass
    
    @abstractmethod
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse interface output from this vendor."""
        pass
    
    def extract_model(self, system_info: SystemInfo) -> Optional[str]:
        """Extract model information from system info."""
        if not system_info or not system_info.sys_descr:
            return None
        
        descr = system_info.sys_descr.lower()
        return self._extract_model_from_description(descr)
    
    @abstractmethod
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Vendor-specific model extraction logic."""
        pass
    
    def get_priority(self) -> int:
        """Return priority for vendor matching (higher = more specific)."""
        return 1
    
    def supports_feature(self, feature: str) -> bool:
        """Check if vendor supports a specific feature."""
        supported_features = getattr(self, '_supported_features', [])
        return feature in supported_features
