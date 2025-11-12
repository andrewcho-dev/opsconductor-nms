import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from jsonschema import validate

from .config import settings
from .schemas import AnalystResponse, InferenceInput, PatchEnvelope
from .json_repair import repair_truncated_json

logger = logging.getLogger(__name__)


class AnalystService:
    def __init__(self) -> None:
        self._schema: Optional[Dict[str, Any]] = None
        self._system_prompt: str = ""
        self._client: Optional[httpx.AsyncClient] = None

    async def startup(self) -> None:
        self._schema = self._load_json_schema(settings.json_schema_path)
        self._system_prompt = self._load_text(settings.system_prompt_path)
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def process(self, payload: InferenceInput) -> AnalystResponse:
        request_body = payload.model_dump(mode="json")
        evidence = request_body.get("evidence_window", {})
        total_items = len(evidence.get("arp", [])) + len(evidence.get("flows", []))
        if total_items > settings.max_evidence_items:
            raise ValueError("evidence window exceeds max_evidence_items")
        if settings.seed_gateway_ip and "gateway_ip" not in request_body.get("seed_facts", {}):
            request_body.setdefault("seed_facts", {})["gateway_ip"] = settings.seed_gateway_ip
        if settings.seed_firewall_ip and "firewall_ip" not in request_body.get("seed_facts", {}):
            request_body.setdefault("seed_facts", {})["firewall_ip"] = settings.seed_firewall_ip
        patch_data = await self._invoke_llm(request_body)
        envelope = PatchEnvelope.model_validate(patch_data)
        applied = await self._apply_patch(envelope)
        return AnalystResponse(
            request_id=payload.evidence_window.window_id,
            patch=envelope,
            applied_graph=applied,
            applied_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _invoke_llm(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": json.dumps(request_body, separators=(",", ":"))},
        ]
        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 1400,
        }
        if settings.response_format == "json_schema" and self._schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "topology_patch", "schema": self._schema},
            }
        elif settings.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        endpoint = f"{settings.normalized_llm_url}/chat/completions"
        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("choices"):
            raise RuntimeError("LLM response missing choices")
        content = data["choices"][0]["message"]["content"]
        
        logger.info(f"Raw LLM response length: {len(content)}")
        logger.info(f"Response head (500 chars): {content[:500]}")
        logger.info(f"Response tail (500 chars): ...{content[-500:]}")
        
        finish_reason = data["choices"][0].get("finish_reason", "unknown")
        logger.info(f"Finish reason: {finish_reason}")
        
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e.msg} at position {e.pos}")
            logger.error(f"Context around error (100 chars before/after): ...{content[max(0, e.pos-100):min(len(content), e.pos+100)]}...")
            logger.warning("Attempting to repair truncated JSON...")
            try:
                repaired = repair_truncated_json(content)
                logger.info(f"Repaired JSON tail: ...{repaired[-200:]}")
                parsed = json.loads(repaired)
                logger.info("JSON repair successful!")
            except Exception as repair_err:
                logger.error(f"JSON repair failed: {repair_err}")
                raise e
            
        if self._schema is not None and settings.response_format == "json_schema":
            validate(parsed, self._schema)
        return parsed

    async def _apply_patch(self, envelope: PatchEnvelope) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        response = await self._client.post(settings.state_patch_url, json=envelope.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _load_json_schema(path: str) -> Optional[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _load_text(path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
