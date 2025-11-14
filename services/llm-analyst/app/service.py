import json
import logging
import ipaddress
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from jsonschema import validate

from .config import settings
from .schemas import AnalystResponse, InferenceInput, PatchEnvelope
from .json_repair import repair_truncated_json

logger = logging.getLogger(__name__)

STATE_SERVER_URL = "http://state-server:8080"


def is_external_ip(ip_str: str) -> bool:
    """Check if an IP address is external (non-RFC1918 private address)."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
        return True
    except ValueError:
        return False


def replace_external_ips(flows: list, arps: list) -> tuple[list, list]:
    """Replace all external IP addresses with 'Internet' in flows and ARP records."""
    modified_flows = []
    for flow in flows:
        flow_copy = flow.copy()
        if flow_copy.get("src_ip") and is_external_ip(flow_copy["src_ip"]):
            flow_copy["src_ip"] = "Internet"
        if flow_copy.get("dst_ip") and is_external_ip(flow_copy["dst_ip"]):
            flow_copy["dst_ip"] = "Internet"
        modified_flows.append(flow_copy)
    
    modified_arps = []
    for arp in arps:
        arp_copy = arp.copy()
        if arp_copy.get("sender_ip") and is_external_ip(arp_copy["sender_ip"]):
            arp_copy["sender_ip"] = "Internet"
        if arp_copy.get("target_ip") and is_external_ip(arp_copy["target_ip"]):
            arp_copy["target_ip"] = "Internet"
        modified_arps.append(arp_copy)
    
    return modified_flows, modified_arps


def discover_networks(all_ips: set[str], seed_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Discover networks by grouping IPs into subnets."""
    networks = {}
    
    if seed_config.get("subnetMask"):
        subnet_mask = seed_config["subnetMask"]
        prefix_len = sum([bin(int(octet)).count('1') for octet in subnet_mask.split('.')])
        
        for ip_str in all_ips:
            if ip_str == "Internet":
                continue
            try:
                ip = ipaddress.ip_address(ip_str)
                network = ipaddress.ip_network(f"{ip}/{prefix_len}", strict=False)
                network_key = str(network)
                
                if network_key not in networks:
                    networks[network_key] = {
                        "cidr": network_key,
                        "label": f"Network {network_key}",
                        "members": [],
                        "kind": "internal",
                        "inferred_mask": f"/{prefix_len}"
                    }
                networks[network_key]["members"].append(ip_str)
            except (ValueError, TypeError):
                pass
    else:
        private_ips = [ip for ip in all_ips if ip != "Internet" and not is_external_ip(ip)]
        if private_ips:
            network_key = "internal"
            networks[network_key] = {
                "cidr": None,
                "label": "Internal Network",
                "members": list(private_ips),
                "kind": "internal",
                "inferred_mask": None
            }
    
    if "Internet" in all_ips:
        networks["Internet"] = {
            "cidr": None,
            "label": "Internet",
            "members": [],
            "kind": "external",
            "inferred_mask": None
        }
    
    return networks


def identify_routers(flows: list, networks: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Identify routers as IPs that bridge networks."""
    routers = {}
    
    ip_to_network = {}
    for net_key, net_info in networks.items():
        for member_ip in net_info["members"]:
            ip_to_network[member_ip] = net_key
    
    for flow in flows:
        src_ip = flow.get("src_ip")
        dst_ip = flow.get("dst_ip")
        
        if not src_ip or not dst_ip:
            continue
        
        src_net = ip_to_network.get(src_ip)
        dst_net = "Internet" if dst_ip == "Internet" else ip_to_network.get(dst_ip)
        
        if src_net and dst_net and src_net != dst_net:
            gateway_candidates = [src_ip, dst_ip]
            for candidate in gateway_candidates:
                if candidate == "Internet":
                    continue
                if candidate not in routers:
                    routers[candidate] = {
                        "ip": candidate,
                        "label": f"Router {candidate}",
                        "kind": "router",
                        "interfaces": [candidate]
                    }
    
    return routers


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
        
        flows = evidence_window.get("flows") or []
        arps = evidence_window.get("arp") or []
        modified_flows, modified_arps = replace_external_ips(flows, arps)
        evidence_window["flows"] = modified_flows
        evidence_window["arp"] = modified_arps
        
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
        
        seed_config = await self._fetch_seed_config()
        confirmed_ips, node_kinds = self._derive_device_candidates(request_body, seed_config)
        
        all_ips = set()
        for flow in modified_flows:
            if flow.get("src_ip"):
                all_ips.add(flow.get("src_ip"))
            if flow.get("dst_ip"):
                all_ips.add(flow.get("dst_ip"))
        for arp in modified_arps:
            if arp.get("sender_ip"):
                all_ips.add(arp.get("sender_ip"))
        
        networks = discover_networks(all_ips, seed_config)
        routers = identify_routers(modified_flows, networks)
        
        if seed_config.get("defaultGateway") and seed_config["defaultGateway"] in all_ips:
            gw_ip = seed_config["defaultGateway"]
            routers[gw_ip] = {
                "ip": gw_ip,
                "label": "Gateway",
                "kind": "gateway",
                "interfaces": [gw_ip]
            }
        
        if seed_config.get("firewallGateway") and seed_config["firewallGateway"] in all_ips:
            fw_ip = seed_config["firewallGateway"]
            routers[fw_ip] = {
                "ip": fw_ip,
                "label": "Firewall",
                "kind": "firewall",
                "interfaces": [fw_ip]
            }
        
        l3_patch_data = self._generate_l3_patch(networks, routers, modified_flows, seed_config)
        envelope = PatchEnvelope.model_validate(l3_patch_data)
        applied = await self._apply_patch(envelope)
        return AnalystResponse(
            request_id=payload.evidence_window.window_id,
            patch=envelope,
            applied_graph=applied,
            applied_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _invoke_llm(self, request_body: Dict[str, Any], confirmed_ips: set[str], node_kinds: dict[str, str], seed_config: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        
        system_prompt = self._system_prompt
        if seed_config:
            hints = []
            if seed_config.get("defaultGateway"):
                hints.append(f"Default gateway: {seed_config['defaultGateway']}")
            if seed_config.get("subnetMask"):
                hints.append(f"Subnet mask: {seed_config['subnetMask']}")
            if seed_config.get("firewallGateway"):
                hints.append(f"Firewall/Internet gateway: {seed_config['firewallGateway']}")
            if seed_config.get("switchIps"):
                hints.append(f"Known L2 switches: {seed_config['switchIps']}")
            
            if hints:
                hint_text = "\n".join(hints)
                system_prompt += f"\n\nSEED HINTS (validate with evidence): {hint_text}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(request_body, separators=(",", ":"))},
        ]
        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0.0,
            "top_p": 0.9,
            "max_tokens": 800,
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

    async def _fetch_seed_config(self) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        try:
            response = await self._client.get(f"{settings.state_server_url.rstrip('/')}/seed")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch seed config: {e}")
            return {}

    def _is_link_local(self, ip: str) -> bool:
        if ip.startswith("169.254."):
            return True
        if ip.startswith("fe80:"):
            return True
        return False

    def _derive_device_candidates(self, request_body: Dict[str, Any], seed_config: Dict[str, Any] = None) -> tuple[set[str], dict[str, str]]:
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
        
        if seed_config:
            if seed_config.get("defaultGateway"):
                gw_ip = seed_config["defaultGateway"]
                node_kinds.setdefault(gw_ip, "gateway")
                confirmed.add(gw_ip)
            if seed_config.get("firewallGateway"):
                fw_ip = seed_config["firewallGateway"]
                node_kinds.setdefault(fw_ip, "firewall")
                confirmed.add(fw_ip)
            if seed_config.get("switchIps"):
                switch_ips = [ip.strip() for ip in seed_config["switchIps"].split(",") if ip.strip()]
                for sw_ip in switch_ips:
                    node_kinds.setdefault(sw_ip, "switch")
                    confirmed.add(sw_ip)
        
        for ip in confirmed:
            node_kinds.setdefault(ip, "observed")
        
        print(f"[CONFIRMED] {sorted(confirmed)}", flush=True)
        logger.info(f"Confirmed devices: {confirmed}")
        return confirmed, node_kinds

    def _generate_l3_patch(self, networks: Dict[str, Dict[str, Any]], routers: Dict[str, Dict[str, Any]], 
                           flows: list, seed_config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate JSON patch for L3 topology (networks, routers, edges)."""
        patch_ops = []
        
        for net_key, net_info in networks.items():
            patch_ops.append({
                "op": "add",
                "path": f"/networks/{net_key.replace('/', '~1')}",
                "value": net_info
            })
        
        for router_ip, router_info in routers.items():
            patch_ops.append({
                "op": "add",
                "path": f"/routers/{router_ip}",
                "value": router_info
            })
        
        ip_to_network = {}
        for net_key, net_info in networks.items():
            for member_ip in net_info["members"]:
                ip_to_network[member_ip] = net_key
        
        network_edges = {}
        for flow in flows:
            src_ip = flow.get("src_ip")
            dst_ip = flow.get("dst_ip")
            
            if not src_ip or not dst_ip:
                continue
            
            src_net = ip_to_network.get(src_ip)
            dst_net = "Internet" if dst_ip == "Internet" else ip_to_network.get(dst_ip)
            
            if src_net and dst_net and src_net != dst_net:
                edge_key = f"{src_net}->{dst_net}"
                
                if edge_key not in network_edges:
                    via_router = None
                    for router_ip in routers.keys():
                        if router_ip in [src_ip, dst_ip]:
                            via_router = router_ip
                            break
                    
                    network_edges[edge_key] = {
                        "src_network": src_net,
                        "dst_network": dst_net,
                        "via_router": via_router,
                        "type": "routes_to",
                        "confidence": 0.9,
                        "evidence": []
                    }
                
                evidence_str = f"flow: {src_ip}→{dst_ip}"
                if evidence_str not in network_edges[edge_key]["evidence"]:
                    network_edges[edge_key]["evidence"].append(evidence_str)
        
        for idx, edge in enumerate(network_edges.values()):
            patch_ops.append({
                "op": "add",
                "path": f"/edges/{idx}",
                "value": edge
            })
        
        rationale = f"Discovered {len(networks)} networks, {len(routers)} routers, {len(network_edges)} inter-network routes"
        
        return {
            "version": "1.0",
            "patch": patch_ops,
            "rationale": rationale,
            "warnings": []
        }

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
        
        original_patch_count = len(patch_data.get("patch", []))
        sanitized_patch_count = len(sanitized_ops)
        
        if original_patch_count > 0 and sanitized_patch_count == 0:
            sanitized["rationale"] = "No new changes (all proposed operations were for existing nodes/edges)"
            logger.info("All patch operations were duplicates, updated rationale")
        elif sanitized_patch_count < original_patch_count:
            dropped = original_patch_count - sanitized_patch_count
            logger.info("Dropped %d duplicate operations out of %d", dropped, original_patch_count)
        
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
    
    async def classify_device(self, device: Dict[str, Any]) -> Dict[str, Any]:
        open_ports = device.get("open_ports") or {}
        snmp_data = device.get("snmp_data") or {}
        vendor = device.get("vendor")
        model = device.get("model")
        
        device_type = None
        confidence = 0.0
        evidence = []
        
        if vendor:
            evidence.append(f"Vendor: {vendor}")
        if model:
            evidence.append(f"Model: {model}")
        
        has_ssh = "22" in open_ports
        has_telnet = "23" in open_ports
        has_http = "80" in open_ports
        has_https = "443" in open_ports
        has_rtsp = "554" in open_ports
        has_mqtt = "1883" in open_ports
        has_sip = "5060" in open_ports
        has_http_alt = "8080" in open_ports
        has_https_alt = "8443" in open_ports
        has_snmp = "161" in open_ports
        has_bgp = "179" in open_ports
        has_rdp = "3389" in open_ports
        
        if has_rtsp:
            device_type = "ip_camera"
            confidence = 0.85
            evidence.append("RTSP streaming port open (554)")
            if has_http_alt or has_http:
                confidence = 0.9
                evidence.append("RTSP with web interface")
        elif has_sip:
            device_type = "voip_phone"
            confidence = 0.85
            evidence.append("SIP protocol port open (5060)")
            if has_https_alt or has_https:
                confidence = 0.9
                evidence.append("SIP with management interface")
        elif has_mqtt and (has_http or has_https):
            device_type = "iot_device"
            confidence = 0.75
            evidence.append("MQTT protocol with web interface")
        elif has_rdp and not has_ssh:
            device_type = "windows_host"
            confidence = 0.8
            evidence.append("RDP port open (3389)")
        elif has_ssh and not has_rdp:
            ssh_banner = open_ports.get("22", {}).get("banner", "")
            if "OpenSSH" in ssh_banner:
                device_type = "linux_host"
                confidence = 0.7
                evidence.append(f"SSH with OpenSSH banner: {ssh_banner}")
            else:
                device_type = "linux_host"
                confidence = 0.6
                evidence.append("SSH port open (22)")
        
        if device_type is None and has_snmp and (has_http or has_https or has_https_alt):
            if has_bgp:
                device_type = "router"
                confidence = 0.9
                evidence.append("BGP port open (179) with SNMP and web")
            elif vendor in ["Cisco", "Juniper", "Arista"]:
                device_type = "router"
                confidence = 0.85
                evidence.append(f"Network vendor {vendor} with SNMP and web")
            elif vendor in ["Ubiquiti", "UniFi", "Ruckus", "Aruba"] or (has_https_alt and has_snmp):
                device_type = "access_point"
                confidence = 0.8
                evidence.append("Wireless vendor or HTTPS-alt (8443) with SNMP")
            else:
                device_type = "network_device"
                confidence = 0.7
                evidence.append("SNMP and web management interfaces")
        
        if device_type is None:
            if has_http or has_https:
                device_type = "web_server"
                confidence = 0.5
                evidence.append("HTTP/HTTPS ports open")
            else:
                device_type = "unknown"
                confidence = 0.1
                evidence.append("No identifying ports found")
        
        return {
            "device_type": device_type,
            "confidence_score": confidence,
            "classification_notes": "; ".join(evidence)
        }
    
    async def classify_inventory_devices(self) -> int:
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized")
        
        try:
            resp = await self._client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
            resp.raise_for_status()
            devices = resp.json()
        except Exception as e:
            logger.error(f"Error fetching inventory: {e}")
            return 0
        
        classified_count = 0
        for device in devices:
            if device.get("device_type_confirmed"):
                continue
            
            ip_address = device.get("ip_address")
            current_type = device.get("device_type")
            
            classification = await self.classify_device(device)
            
            if classification["device_type"] != current_type:
                try:
                    update_resp = await self._client.put(
                        f"{STATE_SERVER_URL}/api/inventory/{ip_address}",
                        json=classification,
                        timeout=10.0
                    )
                    if update_resp.status_code < 300:
                        classified_count += 1
                        logger.info(f"Classified {ip_address} as {classification['device_type']} (confidence: {classification['confidence_score']})")
                except Exception as e:
                    logger.error(f"Error updating device {ip_address}: {e}")
        
        return classified_count
