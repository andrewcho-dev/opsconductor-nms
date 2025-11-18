from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PatchOperation(BaseModel):
    op: Literal["add", "remove", "replace"]
    path: str
    value: Optional[Any] = None

    @model_validator(mode="after")
    def validate_value(cls, values):
        op = values.op
        has_value = values.value is not None
        if op in {"add", "replace"} and not has_value:
            raise ValueError("value is required for add or replace")
        if op == "remove" and has_value:
            raise ValueError("value is not allowed for remove")
        return values


class PatchRequest(BaseModel):
    version: str = "1.0"
    patch: List[PatchOperation]
    rationale: str
    warnings: List[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    src: str
    dst: str
    type: str
    confidence: float
    evidence: List[str]
    notes: Optional[str] = None


class NetworkNode(BaseModel):
    cidr: Optional[str] = None
    label: str
    members: List[str] = Field(default_factory=list)
    kind: str
    inferred_mask: Optional[str] = None


class RouterNode(BaseModel):
    ip: str
    label: str
    kind: str
    interfaces: List[str] = Field(default_factory=list)


class NetworkEdge(BaseModel):
    src_network: str
    dst_network: str
    via_router: Optional[str] = None
    type: str
    confidence: float
    evidence: List[str]


class GraphStatePayload(BaseModel):
    networks: Dict[str, NetworkNode] = Field(default_factory=dict)
    routers: Dict[str, RouterNode] = Field(default_factory=dict)
    edges: List[NetworkEdge] = Field(default_factory=list)
    nodes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    legacy_edges: List[GraphEdge] = Field(default_factory=list)


class GraphResponse(BaseModel):
    graph: GraphStatePayload
    updated_at: datetime


class PatchEventResponse(BaseModel):
    id: int
    patch: List[PatchOperation]
    rationale: str
    warnings: List[str]
    created_at: datetime


class SeedConfigRequest(BaseModel):
    defaultGateway: str = ""
    subnetMask: str = ""
    firewallGateway: str = ""
    switchIps: str = ""


class MibBase(BaseModel):
    name: str
    vendor: Optional[str] = None
    device_types: Optional[List[str]] = None
    version: Optional[str] = None
    description: Optional[str] = None
    oid_prefix: Optional[str] = None


class MibCreate(MibBase):
    file_path: str


class MibResponse(MibBase):
    id: int
    file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class IpInventoryBase(BaseModel):
    ip_address: str
    mac_address: Optional[str] = None
    status: str = 'unknown'
    device_type: Optional[str] = None
    device_type_confirmed: bool = False
    device_name: Optional[str] = None
    network_role: str = "unknown"
    network_role_confirmed: bool = False
    vendor: Optional[str] = None
    model: Optional[str] = None
    hostname: Optional[str] = None
    open_ports: Optional[Dict[str, Any]] = None
    snmp_data: Optional[Dict[str, Any]] = None
    
    snmp_enabled: bool = False
    snmp_port: int = 161
    snmp_version: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_username: Optional[str] = None
    snmp_auth_protocol: Optional[str] = None
    snmp_auth_key: Optional[str] = None
    snmp_priv_protocol: Optional[str] = None
    snmp_priv_key: Optional[str] = None
    mib_id: Optional[int] = None
    mib_ids: Optional[List[int]] = None
    
    confidence_score: Optional[float] = None
    classification_notes: Optional[str] = None


class IpInventoryCreate(IpInventoryBase):
    pass


class IpInventoryUpdate(BaseModel):
    mac_address: Optional[str] = None
    status: Optional[str] = None
    device_type: Optional[str] = None
    device_type_confirmed: Optional[bool] = None
    device_name: Optional[str] = None
    network_role: Optional[str] = None
    network_role_confirmed: Optional[bool] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    hostname: Optional[str] = None
    open_ports: Optional[Dict[str, Any]] = None
    snmp_data: Optional[Dict[str, Any]] = None
    snmp_enabled: Optional[bool] = None
    snmp_port: Optional[int] = None
    snmp_version: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_username: Optional[str] = None
    snmp_auth_protocol: Optional[str] = None
    snmp_auth_key: Optional[str] = None
    snmp_priv_protocol: Optional[str] = None
    snmp_priv_key: Optional[str] = None
    mib_id: Optional[int] = None
    mib_ids: Optional[List[int]] = None
    confidence_score: Optional[float] = None
    classification_notes: Optional[str] = None


class IpInventoryResponse(IpInventoryBase):
    id: int
    first_seen: datetime
    last_seen: datetime
    last_probed: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator('ip_address', mode='before')
    @classmethod
    def convert_ip_address(cls, v):
        if isinstance(v, (IPv4Address, IPv6Address)):
            return str(v)
        return v

    class Config:
        from_attributes = True


class DeviceConfirmationCreate(BaseModel):
    confirmed_by: str
    confirmed_type: str
    confidence: float
    evidence: Optional[str] = None


class DeviceConfirmationResponse(BaseModel):
    id: int
    ip_inventory_id: int
    confirmed_by: str
    confirmed_type: str
    confidence: float
    evidence: Optional[str] = None
    confirmed_at: datetime

    class Config:
        from_attributes = True


class TerminalLaunchRequest(BaseModel):
    terminal_path: str
    command_template: str
    host: str
    port: int
    protocol: str


class FileSystemItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[str] = None
