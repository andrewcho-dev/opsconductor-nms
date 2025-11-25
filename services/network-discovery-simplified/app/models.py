from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class DiscoveryRun(Base):
    __tablename__ = 'discovery_runs'
    
    id = Column(Integer, primary_key=True)
    status = Column(String(20), default='PENDING')  # PENDING, RUNNING, COMPLETED, FAILED
    root_ip = Column(String(15), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    routers_found = Column(Integer, default=0)
    routes_found = Column(Integer, default=0)
    networks_found = Column(Integer, default=0)
    
    # Relationships
    routers = relationship("Router", back_populates="discovery_run")
    routes = relationship("Route", back_populates="discovery_run")
    networks = relationship("Network", back_populates="discovery_run")


class Router(Base):
    __tablename__ = 'routers'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    ip_address = Column(String(15), nullable=False, unique=True)
    hostname = Column(String(255), nullable=True)
    vendor = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    sys_descr = Column(Text, nullable=True)
    is_router = Column(Boolean, default=False)
    router_score = Column(Float, default=0.0)
    classification_reason = Column(Text, nullable=True)
    discovered_via = Column(String(20), default='snmp')  # snmp, cli, both
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="routers")
    routes = relationship("Route", back_populates="router")
    networks = relationship("Network", back_populates="router")


class Route(Base):
    __tablename__ = 'routes'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    router_id = Column(Integer, ForeignKey('routers.id'), nullable=False)
    destination = Column(String(18), nullable=False)  # CIDR notation
    next_hop = Column(String(15), nullable=True)
    protocol = Column(String(20), nullable=True)  # connected, static, ospf, bgp, etc.
    admin_distance = Column(Integer, nullable=True)
    metric = Column(Integer, nullable=True)
    discovered_via = Column(String(20), default='snmp')  # snmp, cli
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="routes")
    router = relationship("Router", back_populates="routes")


class Network(Base):
    __tablename__ = 'networks'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    router_id = Column(Integer, ForeignKey('routers.id'), nullable=False)
    network = Column(String(18), nullable=False)  # CIDR notation
    interface = Column(String(50), nullable=True)
    is_connected = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun", back_populates="networks")
    router = relationship("Router", back_populates="networks")


class TopologyLink(Base):
    __tablename__ = 'topology_links'
    
    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(Integer, ForeignKey('discovery_runs.id'), nullable=False)
    from_router_id = Column(Integer, ForeignKey('routers.id'), nullable=False)
    to_router_id = Column(Integer, ForeignKey('routers.id'), nullable=False)
    shared_network = Column(String(18), nullable=False)  # The network that connects them
    link_type = Column(String(20), default='direct')  # direct, indirect
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    discovery_run = relationship("DiscoveryRun")
    from_router = relationship("Router", foreign_keys=[from_router_id])
    to_router = relationship("Router", foreign_keys=[to_router_id])
