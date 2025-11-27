from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class DiscoveryRun(Base):
    __tablename__ = 'discovery_runs'
    
    id = Column(Integer, primary_key=True)
    status = Column(String(20), default='PENDING')  # PENDING, RUNNING, COMPLETED, FAILED
    root_ip = Column(String(45), nullable=False)  # Support IPv6
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Summary statistics (denormalized for performance)
    routers_found = Column(Integer, default=0)
    routes_found = Column(Integer, default=0)
    networks_found = Column(Integer, default=0)
    links_found = Column(Integer, default=0)
    
    # Configuration snapshot
    config_snmp_community = Column(String(100), nullable=True)
    config_timeout = Column(Integer, nullable=True)
    config_networks = Column(Text, nullable=True)  # JSON array of networks
    
    # Relationships
    routers = relationship("Router", back_populates="discovery_run", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="discovery_run", cascade="all, delete-orphan")
    networks = relationship("Network", back_populates="discovery_run", cascade="all, delete-orphan")
    links = relationship("Link", back_populates="discovery_run", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_discovery_runs_status', 'status'),
        Index('idx_discovery_runs_started', 'started_at'),
    )


class Device(Base):
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    
    # Network identification
    ip_address = Column(String(45), nullable=False)  # IPv4/IPv6 compatible
    hostname = Column(String(255), nullable=True)
    
    # Device classification
    device_type = Column(String(20), default='unknown')  # router, switch, firewall, host, unknown
    vendor = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    os_version = Column(String(100), nullable=True)
    
    # Device capabilities
    is_router = Column(Boolean, default=False)
    is_switch = Column(Boolean, default=False)
    layer3_capable = Column(Boolean, default=False)
    
    # Discovery metadata
    sys_descr = Column(Text, nullable=True)
    sys_uptime = Column(Integer, nullable=True)  # SNMP uptime in ticks
    classification_reason = Column(Text, nullable=True)
    discovery_confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    
    # Discovery methods
    discovered_via = Column(String(20), default='snmp')  # snmp, cli, both, ping
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="routers")
    routes = relationship("Route", back_populates="device", cascade="all, delete-orphan")
    networks = relationship("Network", back_populates="device", cascade="all, delete-orphan")
    links_from = relationship("Link", foreign_keys="Link.from_device_id", back_populates="from_device", cascade="all, delete-orphan")
    links_to = relationship("Link", foreign_keys="Link.to_device_id", back_populates="to_device", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('discovery_run_id', 'ip_address', name='uq_device_ip_per_run'),
        Index('idx_devices_ip', 'ip_address'),
        Index('idx_devices_hostname', 'hostname'),
        Index('idx_devices_type', 'device_type'),
        Index('idx_devices_discovery_run', 'discovery_run_id'),
    )


class Route(Base):
    __tablename__ = 'routes'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    
    # Route information
    destination = Column(String(45), nullable=False)  # Network/CIDR (IPv6 compatible)
    destination_prefix = Column(Integer, nullable=False)  # CIDR prefix length
    next_hop = Column(String(45), nullable=True)  # Next hop IP
    next_hop_type = Column(String(20), default='ip')  # ip, interface, null
    
    # Route attributes
    protocol = Column(String(20), nullable=True)  # connected, static, ospf, bgp, eigrp, rip
    admin_distance = Column(Integer, nullable=True)
    metric = Column(Integer, nullable=True)
    route_tag = Column(Integer, nullable=True)
    
    # Status and metadata
    is_active = Column(Boolean, default=True)
    discovered_via = Column(String(20), default='snmp')  # snmp, cli
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="routes")
    device = relationship("Device", back_populates="routes")
    
    __table_args__ = (
        UniqueConstraint('device_id', 'destination', 'destination_prefix', 'next_hop', name='uq_route_unique'),
        Index('idx_routes_destination', 'destination'),
        Index('idx_routes_device', 'device_id'),
        Index('idx_routes_protocol', 'protocol'),
        Index('idx_routes_discovery_run', 'discovery_run_id'),
    )


class Network(Base):
    __tablename__ = 'networks'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    
    # Network information
    network_address = Column(String(45), nullable=False)  # Network IP
    prefix_length = Column(Integer, nullable=False)  # CIDR prefix
    network_mask = Column(String(45), nullable=True)  # Subnet mask (IPv4)
    
    # Interface information
    interface_name = Column(String(100), nullable=True)
    interface_type = Column(String(50), nullable=True)  # ethernet, serial, vlan, loopback
    interface_speed = Column(Integer, nullable=True)  # Mbps
    interface_status = Column(String(20), default='unknown')  # up, down, unknown
    
    # Network properties
    is_connected = Column(Boolean, default=True)
    is_management = Column(Boolean, default=False)  # Management network
    is_transit = Column(Boolean, default=False)  # Transit network
    
    # Addressing
    ip_address = Column(String(45), nullable=True)  # Device IP on this network
    subnet = Column(String(45), nullable=False)  # Full CIDR notation
    
    # Metadata
    discovered_via = Column(String(20), default='snmp')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="networks")
    device = relationship("Device", back_populates="networks")
    
    __table_args__ = (
        UniqueConstraint('device_id', 'subnet', name='uq_network_device_subnet'),
        Index('idx_networks_address', 'network_address'),
        Index('idx_networks_subnet', 'subnet'),
        Index('idx_networks_device', 'device_id'),
        Index('idx_networks_discovery_run', 'discovery_run_id'),
    )


class Link(Base):
    __tablename__ = 'links'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    
    # Link endpoints
    from_device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    to_device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    
    # Network context
    shared_network = Column(String(45), nullable=False)  # Network connecting the devices
    shared_network_prefix = Column(Integer, nullable=False)
    
    # Link properties
    link_type = Column(String(20), default='direct')  # direct, indirect, layer2, tunnel
    link_protocol = Column(String(20), nullable=True)  # ethernet, serial, fiber, wireless
    
    # Interface information
    from_interface = Column(String(100), nullable=True)
    to_interface = Column(String(100), nullable=True)
    
    # Performance metrics
    bandwidth_mbps = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    utilization_percent = Column(Float, nullable=True)
    
    # Discovery and verification
    discovery_method = Column(String(20), nullable=False)  # traceroute, routing_table, lldp, cdp
    initial_discovery = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_verified = Column(DateTime, nullable=False, default=datetime.utcnow)
    verification_count = Column(Integer, default=1)
    
    # Status and visualization
    status = Column(String(20), default='active')  # active, failed, deprecated, unknown
    is_bidirectional = Column(Boolean, default=True)
    
    # Visualization properties
    color = Column(String(7), nullable=True)  # Hex color code
    width = Column(Integer, default=2)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="links")
    from_device = relationship("Device", foreign_keys=[from_device_id], back_populates="links_from")
    to_device = relationship("Device", foreign_keys=[to_device_id], back_populates="links_to")
    
    __table_args__ = (
        UniqueConstraint('from_device_id', 'to_device_id', 'shared_network', name='uq_link_unique'),
        Index('idx_links_from_device', 'from_device_id'),
        Index('idx_links_to_device', 'to_device_id'),
        Index('idx_links_network', 'shared_network'),
        Index('idx_links_type', 'link_type'),
        Index('idx_links_status', 'status'),
        Index('idx_links_discovery_run', 'discovery_run_id'),
    )


# Migration helper class
class SchemaMigration:
    """Helper class for migrating from old schema to new consolidated schema."""
    
    @staticmethod
    def get_migration_summary():
        """Get summary of changes made."""
        return {
            'tables_consolidated': {
                'routers': 'devices (expanded capabilities)',
                'topology_links + network_links': 'links (unified)',
                'networks': 'networks (enhanced)',
                'routes': 'routes (enhanced)',
                'discovery_runs': 'discovery_runs (enhanced)'
            },
            'key_improvements': [
                'IPv6 support (String(45) for IPs)',
                'Proper indexing strategy',
                'Unique constraints to prevent duplicates',
                'Consistent naming conventions',
                'Enhanced device classification',
                'Performance metrics tracking',
                'Bidirectional link support',
                'Interface-level detail',
                'Configuration snapshot storage'
            ],
            'performance_improvements': [
                'Strategic indexes on foreign keys and query fields',
                'Denormalized summary statistics in discovery_runs',
                'Composite unique constraints for data integrity',
                'Cascade delete for proper cleanup'
            ]
        }
