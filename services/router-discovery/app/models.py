from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import INET, CIDR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

Base = declarative_base()


class DiscoveryRun(Base):
    __tablename__ = 'discovery_runs'
    
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default='PENDING')  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    root_ip = Column(INET, nullable=False)
    snmp_community = Column(String, nullable=False)
    snmp_version = Column(String, nullable=False)  # "2c" or "3"
    error_message = Column(Text, nullable=True)
    cli_default_credentials = Column(JSON, nullable=False, default=list)
    
    # Relationships
    routers = relationship('Router', back_populates='run', cascade='all, delete-orphan')
    router_networks = relationship('RouterNetwork', back_populates='run', cascade='all, delete-orphan')
    router_routes = relationship('RouterRoute', back_populates='run', cascade='all, delete-orphan')
    topology_edges = relationship('TopologyEdge', back_populates='run', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_discovery_runs_status', 'status'),
        Index('idx_discovery_runs_started_at', 'started_at'),
    )


class Router(Base):
    __tablename__ = 'routers'
    
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('discovery_runs.id', ondelete='CASCADE'), nullable=False)
    primary_ip = Column(INET, nullable=False)
    hostname = Column(String, nullable=True)
    sys_descr = Column(Text, nullable=True)
    sys_object_id = Column(String, nullable=True)
    vendor = Column(String, nullable=True)
    model = Column(String, nullable=True)
    is_router = Column(Boolean, nullable=False)
    router_score = Column(Integer, nullable=False)
    classification_reason = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    run = relationship('DiscoveryRun', back_populates='routers')
    networks = relationship('RouterNetwork', back_populates='router', cascade='all, delete-orphan')
    routes = relationship('RouterRoute', back_populates='router', cascade='all, delete-orphan')
    edges_from = relationship(
        'TopologyEdge',
        foreign_keys='TopologyEdge.from_router_id',
        back_populates='from_router',
        cascade='all, delete-orphan'
    )
    edges_to = relationship(
        'TopologyEdge',
        foreign_keys='TopologyEdge.to_router_id',
        back_populates='to_router',
        cascade='all, delete-orphan'
    )
    
    __table_args__ = (
        UniqueConstraint('run_id', 'primary_ip'),
        Index('idx_routers_run_id', 'run_id'),
        Index('idx_routers_run_id_is_router', 'run_id', 'is_router'),
    )


class RouterNetwork(Base):
    __tablename__ = 'router_networks'
    
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('discovery_runs.id', ondelete='CASCADE'), nullable=False)
    router_id = Column(Integer, ForeignKey('routers.id', ondelete='CASCADE'), nullable=False)
    network = Column(CIDR, nullable=False)
    is_local = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    run = relationship('DiscoveryRun', back_populates='router_networks')
    router = relationship('Router', back_populates='networks')
    
    __table_args__ = (
        Index('idx_router_networks_run_id_router_id', 'run_id', 'router_id'),
        Index('idx_router_networks_run_id_network', 'run_id', 'network'),
    )


class RouterRoute(Base):
    __tablename__ = 'router_routes'
    
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('discovery_runs.id', ondelete='CASCADE'), nullable=False)
    router_id = Column(Integer, ForeignKey('routers.id', ondelete='CASCADE'), nullable=False)
    destination = Column(CIDR, nullable=False)
    next_hop = Column(INET, nullable=True)
    protocol = Column(String, nullable=True)
    admin_distance = Column(Integer, nullable=True)
    metric = Column(Integer, nullable=True)
    
    # Relationships
    run = relationship('DiscoveryRun', back_populates='router_routes')
    router = relationship('Router', back_populates='routes')
    
    __table_args__ = (
        Index('idx_router_routes_run_id_router_id', 'run_id', 'router_id'),
        Index('idx_router_routes_run_id_destination', 'run_id', 'destination'),
    )


class TopologyEdge(Base):
    __tablename__ = 'topology_edges'
    
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey('discovery_runs.id', ondelete='CASCADE'), nullable=False)
    from_router_id = Column(Integer, ForeignKey('routers.id', ondelete='CASCADE'), nullable=False)
    to_router_id = Column(Integer, ForeignKey('routers.id', ondelete='CASCADE'), nullable=False)
    reason = Column(String, nullable=False)
    
    # Relationships
    run = relationship('DiscoveryRun', back_populates='topology_edges')
    from_router = relationship('Router', foreign_keys=[from_router_id], back_populates='edges_from')
    to_router = relationship('Router', foreign_keys=[to_router_id], back_populates='edges_to')
    
    __table_args__ = (
        UniqueConstraint('run_id', 'from_router_id', 'to_router_id'),
        Index('idx_topology_edges_run_id', 'run_id'),
    )
