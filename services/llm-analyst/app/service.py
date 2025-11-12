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
        evidence_window = request_body.get("evidence_window", {})
        flows = evidence_window.get("flows") or []
        original_src_ips = {f.get("src_ip") for f in flows if f.get("src_ip")}
        if "192.168.10.10" in original_src_ips:
            print(f"[RAW_PAYLOAD] 192.168.10.10 IN original payload, flows={len(flows)}", flush=True)
        arps = evidence_window.get("arp") or []
        if len(flows) > settings.max_flow_items:
            trimmed = flows[: settings.max_flow_items]
            logger.debug("Trimming flows from %d to %d", len(flows), len(trimmed))
            evidence_window["flows"] = trimmed
        if len(arps) > settings.max_arp_items:
            trimmed = arps[: settings.max_arp_items]
            logger.debug("Trimming ARP entries from %d to %d", len(arps), len(trimmed))
            evidence_window["arp"] = trimmed
        total_items = len(evidence_window.get("arp", [])) + len(evidence_window.get("flows", []))
        if total_items > settings.max_evidence_items:
            raise ValueError("evidence window exceeds max_evidence_items")
        logger.debug(
            "Prepared evidence window: %d items (flows=%d, arp=%d), payload size=%d chars",
            total_items,
            len(evidence_window.get("flows", [])),
            len(evidence_window.get("arp", [])),
            len(json.dumps(request_body, separators=(",", ":"))),
        )
        if settings.seed_gateway_ip and "gateway_ip" not in request_body.get("seed_facts", {}):
            request_body.setdefault("seed_facts", {})["gateway_ip"] = settings.seed_gateway_ip
        if settings.seed_firewall_ip and "firewall_ip" not in request_body.get("seed_facts", {}):
            request_body.setdefault("seed_facts", {})["firewall_ip"] = settings.seed_firewall_ip
        confirmed_ips, node_kinds = self._derive_device_candidates(request_body)
        patch_data = await self._invoke_llm(request_body, confirmed_ips, node_kinds)
        sanitized = await self._sanitize_patch(patch_data, confirmed_ips, node_kinds)
        envelope = PatchEnvelope.model_validate(sanitized)
        applied = await self._apply_patch(envelope)
        return AnalystResponse(
            request_id=payload.evidence_window.window_id,
            patch=envelope,
            applied_graph=applied,
            applied_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _invoke_llm(self, request_body: Dict[str, Any], confirmed_ips: set[str], node_kinds: dict[str, str]) -> Dict[str, Any]:
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
            "max_tokens": 1200,
        }
        if settings.response_format == "json_schema" and self._schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "topology_patch", "schema": self._schema},
            }
        elif settings.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        endpoint = f"{settings.normalized_llm_url}/chat/completions"
        logger.info(f"Attempting LLM request to: {endpoint}")
        try:
            response = await self._client.post(endpoint, json=payload)
        except httpx.RequestError as err:
            logger.error(f"LLM request exception to {endpoint}: {err}", exc_info=True)
            return await self._fallback_patch(request_body, f"http_request_error:{err}", confirmed_ips, node_kinds)
        if response.status_code >= 400:
            logger.error("LLM request failed: %s %s", response.status_code, response.text)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as err:
                return await self._fallback_patch(request_body, f"http_status_error:{err.response.status_code}", confirmed_ips, node_kinds)
            return await self._fallback_patch(request_body, "http_status_error", confirmed_ips, node_kinds)
        data = response.json()
        if not data.get("choices"):
            logger.error("LLM response missing choices: %s", data)
            return await self._fallback_patch(request_body, "missing_choices", confirmed_ips, node_kinds)
        content = data["choices"][0]["message"]["content"]

        logger.info(f"Raw LLM response length: {len(content)}")
        logger.info(f"Response head (500 chars): {content[:500]}")
        logger.info(f"Response tail (500 chars): ...{content[-500:]}")

        finish_reason = data["choices"][0].get("finish_reason", "unknown")
        logger.info(f"Finish reason: {finish_reason}")

        normalized_content = self._strip_code_fence(content)
        candidates: list[str] = []
        fragment = self._extract_json_fragment(normalized_content)
        if fragment:
            candidates.append(fragment.strip())
        normalized_candidate = normalized_content.strip()
        if normalized_candidate and normalized_candidate not in candidates:
            candidates.append(normalized_candidate)
        parsed: Optional[Dict[str, Any]] = None
        last_error: Optional[json.JSONDecodeError] = None
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError as decode_err:
                last_error = decode_err
                logger.error(f"JSON decode error: {decode_err.msg} at position {decode_err.pos}")
                logger.error(f"Context around error (100 chars before/after): ...{candidate[max(0, decode_err.pos - 100):min(len(candidate), decode_err.pos + 100)]}...")
                logger.warning("Attempting to repair truncated JSON...")
                try:
                    repaired = repair_truncated_json(candidate)
                    logger.info(f"Repaired JSON tail: ...{repaired[-200:]}")
                    parsed = json.loads(repaired)
                    logger.info("JSON repair successful!")
                    break
                except Exception as repair_err:
                    logger.error(f"JSON repair failed: {repair_err}")
        if parsed is None:
            reason = f"json_decode_error:{last_error.msg}" if last_error else "json_decode_error:unknown"
            return await self._fallback_patch(request_body, reason, confirmed_ips, node_kinds)

        if isinstance(parsed, dict):
            patch_ops = parsed.get("patch")
            if isinstance(patch_ops, list) and len(patch_ops) > settings.max_patch_operations:
                logger.warning(
                    "Truncating patch operations from %d to %d",
                    len(patch_ops),
                    settings.max_patch_operations,
                )
                parsed["patch"] = patch_ops[: settings.max_patch_operations]

        if self._schema is not None and settings.response_format == "json_schema":
            validate(parsed, self._schema)
        return parsed

    async def _fallback_patch(self, request_body: Dict[str, Any], reason: str, confirmed_ips: set[str], node_kinds: dict[str, str]) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        logger.warning("Falling back to heuristic patch: %s", reason)
        known_nodes = set()
        existing_edges = set()
        try:
            snapshot = await self._fetch_graph_snapshot()
            known_nodes = set((snapshot.get("nodes", {}) or {}).keys())
            existing_edges = {
                (edge.get("src"), edge.get("dst"), edge.get("type"))
                for edge in (snapshot.get("edges", []) or [])
                if isinstance(edge, dict)
            }
        except Exception as fetch_err:
            logger.error("Unable to load current graph during fallback: %s", fetch_err)
            known_nodes = set()
            existing_edges = set()

        evidence = request_body.get("evidence_window", {})
        flows = evidence.get("flows", [])
        arps = evidence.get("arp", [])
        local_node_kinds = dict(node_kinds)
        for ip in confirmed_ips:
            local_node_kinds.setdefault(ip, "observed")

        operations: list[Dict[str, Any]] = []

        def ensure_capacity(required: int) -> bool:
            return len(operations) + required <= settings.max_patch_operations

        def add_node(ip: Optional[str]) -> None:
            if not ip or ip in known_nodes or not ensure_capacity(1):
                return
            kind = local_node_kinds.get(ip)
            if not kind:
                return
            operations.append({
                "op": "add",
                "path": f"/nodes/{ip}",
                "value": {"ip": ip, "kind": kind},
            })
            known_nodes.add(ip)

        def add_edge(src: Optional[str], dst: Optional[str], edge_type: str, confidence: float, evidence_id: str) -> None:
            if not src or not dst:
                return
            if src not in local_node_kinds and src not in known_nodes:
                return
            if dst not in local_node_kinds and dst not in known_nodes:
                return
            key = (src, dst, edge_type)
            if key in existing_edges:
                return
            if not ensure_capacity(1):
                return
            operations.append({
                "op": "add",
                "path": "/edges/-",
                "value": {
                    "src": src,
                    "dst": dst,
                    "type": edge_type,
                    "confidence": max(0.0, min(confidence, 1.0)),
                    "evidence": [evidence_id],
                },
            })
            existing_edges.add(key)

        for flow in flows:
            if len(operations) >= settings.max_patch_operations:
                break
            src = flow.get("src_ip")
            dst = flow.get("dst_ip")
            required_slots = (0 if src in known_nodes else 1) + (0 if dst in known_nodes else 1) + 1
            if not ensure_capacity(required_slots):
                continue
            add_node(src)
            add_node(dst)
            proto = (flow.get("protocol") or "").lower()
            edge_type = "tcp" if proto == "tcp" else "inferred_l3"
            evidence_id = flow.get("id") or flow.get("evidence_id") or (
                (flow.get("timestamp") or "fallback") + "#flow"
            )
            add_edge(src, dst, edge_type, 0.9 if edge_type == "tcp" else 0.85, evidence_id)

        arps = evidence.get("arp", [])
        for arp in arps:
            if len(operations) >= settings.max_patch_operations:
                break
            op = str(arp.get("operation") or "").lower()
            if op not in {"reply", "response", "is-at"}:
                continue
            src = arp.get("src_ip")
            dst = arp.get("dst_ip")
            required_slots = (0 if src in known_nodes else 1) + (0 if dst in known_nodes else 1) + 1
            if not ensure_capacity(required_slots):
                continue
            add_node(src)
            add_node(dst)
            evidence_id = arp.get("id") or arp.get("timestamp") or "fallback#arp"
            add_edge(src, dst, "arp", 0.7, str(evidence_id))

        if not operations:
            fallback_ip = next(iter(known_nodes), None)
            if not fallback_ip:
                candidate = None
                if flows:
                    candidate = flows[0].get("src_ip") or flows[0].get("dst_ip")
                if not candidate and arps:
                    candidate = arps[0].get("src_ip") or arps[0].get("dst_ip")
                if candidate:
                    local_node_kinds.setdefault(candidate, "observed")
                    add_node(candidate)
                    fallback_ip = candidate if candidate in known_nodes else fallback_ip
            if fallback_ip and ensure_capacity(1):
                timestamp = evidence.get("window_id") or datetime.now(timezone.utc).isoformat()
                operations.append({
                    "op": "add",
                    "path": f"/nodes/{fallback_ip}/last_seen",
                    "value": timestamp,
                })

        if not operations:
            raise RuntimeError("Fallback patch generation failed: no operations available")

        return {
            "version": "1.0",
            "patch": operations,
            "rationale": f"Fallback patch applied due to LLM failure: {reason}",
            "warnings": [
                "llm_fallback",
                f"original_reason:{reason}",
            ],
        }

    async def _apply_patch(self, envelope: PatchEnvelope) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        response = await self._client.post(settings.state_patch_url, json=envelope.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    async def _fetch_graph_snapshot(self) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        response = await self._client.get(f"{settings.state_server_url.rstrip('/')}/graph")
        response.raise_for_status()
        payload = response.json()
        graph = payload.get("graph") if isinstance(payload, dict) else None
        if isinstance(graph, dict):
            return graph
        return {}

    def _is_link_local(self, ip: str) -> bool:
        if ip.startswith("169.254."):
            return True
        if ip.startswith("fe80:"):
            return True
        return False

    def _derive_device_candidates(self, request_body: Dict[str, Any]) -> tuple[set[str], dict[str, str]]:
        evidence = request_body.get("evidence_window", {}) or {}
        flows = evidence.get("flows", []) or []
        arps = evidence.get("arp", []) or []
        
        confirmed: set[str] = set()
        all_src_ips = set()
        
        for flow in flows:
            src = flow.get("src_ip")
            if src:
                all_src_ips.add(src)
            if src and not self._is_link_local(src):
                confirmed.add(src)
        
        print(f"[ANALYST_FLOWS] all_src={sorted(all_src_ips)} confirmed={sorted(confirmed)}", flush=True)
        
        for arp in arps:
            op = str(arp.get("operation") or "").lower()
            if op in {"reply", "response", "is-at"}:
                src = arp.get("src_ip")
                if src and not self._is_link_local(src):
                    confirmed.add(src)
        
        seed_facts = request_body.get("seed_facts", {}) or {}
        gateway_ip = seed_facts.get("gateway_ip") or settings.seed_gateway_ip
        firewall_ip = seed_facts.get("firewall_ip") or settings.seed_firewall_ip
        node_kinds: dict[str, str] = {}
        if gateway_ip:
            node_kinds[gateway_ip] = "gateway"
            confirmed.add(gateway_ip)
        if firewall_ip:
            node_kinds[firewall_ip] = "firewall"
            confirmed.add(firewall_ip)
        for ip in confirmed:
            node_kinds.setdefault(ip, "observed")
        
        print(f"[CONFIRMED] {sorted(confirmed)}", flush=True)
        logger.info(f"Confirmed devices: {confirmed}")
        return confirmed, node_kinds

    async def _sanitize_patch(self, patch_data: Dict[str, Any], confirmed_ips: set[str], node_kinds: dict[str, str]) -> Dict[str, Any]:
        if not isinstance(patch_data, dict):
            return patch_data
        allowed_ips = set(confirmed_ips)
        allowed_ips.update(node_kinds.keys())
        
        try:
            snapshot = await self._fetch_graph_snapshot()
            existing_nodes = set((snapshot.get("nodes", {}) or {}).keys())
            existing_edges = list(snapshot.get("edges", []) or [])
            existing_edge_keys = {
                (edge.get("src"), edge.get("dst"), edge.get("type"))
                for edge in existing_edges
                if isinstance(edge, dict)
            }
        except Exception as err:
            logger.error("Failed to fetch graph snapshot at start of sanitization: %s", err)
            existing_nodes = set()
            existing_edges = []
            existing_edge_keys = set()
        
        patch_ops = patch_data.get("patch")
        sanitized_ops: list[Dict[str, Any]] = []
        if isinstance(patch_ops, list):
            for entry in patch_ops:
                if not isinstance(entry, dict):
                    continue
                op = entry.get("op")
                path = entry.get("path")
                if isinstance(path, str) and path.startswith("/nodes/"):
                    parts = path.split("/", 3)
                    ip = parts[2] if len(parts) > 2 else ""
                    if op in {"add", "replace"} and ip not in allowed_ips:
                        logger.debug("Dropping node operation for unconfirmed ip: %s", ip)
                        continue
                    if op == "add" and ip in existing_nodes:
                        logger.debug("Skipping duplicate node add: %s", ip)
                        continue
                    value = entry.get("value")
                    if op == "add" and isinstance(value, dict):
                        value.setdefault("ip", ip)
                        value.setdefault("kind", node_kinds.get(ip, "observed"))
                if op == "add" and isinstance(path, str) and path.startswith("/edges"):
                    value = entry.get("value")
                    if not isinstance(value, dict):
                        continue
                    src = value.get("src")
                    dst = value.get("dst")
                    edge_type = value.get("type")
                    if src not in allowed_ips or dst not in allowed_ips:
                        logger.debug("Dropping edge add for unconfirmed endpoints: %s -> %s", src, dst)
                        continue
                    edge_key = (src, dst, edge_type)
                    if edge_key in existing_edge_keys:
                        logger.debug("Skipping duplicate edge add: %s -> %s (%s)", src, dst, edge_type)
                        continue
                sanitized_ops.append(entry)
                if len(sanitized_ops) >= settings.max_patch_operations:
                    break
        sanitized = dict(patch_data)
        sanitized["patch"] = sanitized_ops
        return sanitized

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            remainder = value[3:]
            if "\n" in remainder:
                remainder = remainder.split("\n", 1)[1]
            else:
                remainder = ""
            value = remainder
        if "```" in value:
            value = value.split("```", 1)[0]
        return value.strip()

    @staticmethod
    def _extract_json_fragment(text: str) -> Optional[str]:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"' and not escape:
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:index + 1]
        return text[start:]

    @staticmethod
    def _load_json_schema(path: str) -> Optional[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _load_text(path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
