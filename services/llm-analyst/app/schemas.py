from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class EvidenceWindow(BaseModel):
    window_id: str
    arp: List[Dict[str, Any]] = Field(default_factory=list)
    flows: List[Dict[str, Any]] = Field(default_factory=list)


class InferenceInput(BaseModel):
    seed_facts: Dict[str, Any] = Field(default_factory=dict)
    hypothesis_digest: Dict[str, Any] = Field(default_factory=dict)
    evidence_window: EvidenceWindow
    previous_rationales: List[str] = Field(default_factory=list)


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


class PatchEnvelope(BaseModel):
    version: str = "1.0"
    patch: List[PatchOperation]
    rationale: str
    warnings: List[str] = Field(default_factory=list)


class AnalystResponse(BaseModel):
    request_id: str
    patch: PatchEnvelope
    applied_graph: Dict[str, Any]
    applied_at: str
