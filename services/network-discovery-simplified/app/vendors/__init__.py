"""
Modular vendor discovery system.
"""

from .base import VendorDiscoveryBase
from .cisco import CiscoDiscovery
from .juniper import JuniperDiscovery
from .asa import AsaDiscovery
from .cradlepoint import CradlepointDiscovery
from .mikrotik import MikrotikDiscovery
from .factory import VendorDiscoveryFactory

vendor_factory = VendorDiscoveryFactory()

__all__ = [
    'VendorDiscoveryBase',
    'CiscoDiscovery',
    'JuniperDiscovery', 
    'AsaDiscovery',
    'CradlepointDiscovery',
    'MikrotikDiscovery',
    'VendorDiscoveryFactory',
    'vendor_factory'
]
