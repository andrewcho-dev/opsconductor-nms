from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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


class GraphStatePayload(BaseModel):
    nodes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list)


class GraphResponse(BaseModel):
    graph: GraphStatePayload
    updated_at: datetime


class PatchEventResponse(BaseModel):
    id: int
    patch: List[PatchOperation]
    rationale: str
    warnings: List[str]
    created_at: datetime
