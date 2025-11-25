"""
Common types for the network discovery service.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SystemInfo:
    hostname: Optional[str] = None
    sys_descr: Optional[str] = None
    sys_object_id: Optional[str] = None


@dataclass
class RouteEntry:
    destination: str
    netmask: str
    next_hop: Optional[str] = None
    protocol: Optional[str] = None


@dataclass
class CLIRouteEntry:
    destination: str
    prefix_length: int
    next_hop: Optional[str]
    protocol: Optional[str]
