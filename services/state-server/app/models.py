from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base


class GraphState(Base):
    __tablename__ = "graph_state"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    graph = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PatchEvent(Base):
    __tablename__ = "patch_events"

    id = Column(Integer, primary_key=True)
    patch = Column(JSONB, nullable=False)
    rationale = Column(String, nullable=False)
    warnings = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
