import asyncio
import os
import re
import time
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

import httpx
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    walk_cmd,
    get_cmd,
)
from pysnmp.smi import builder, view, compiler


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://state-server:8080")
WALK_INTERVAL_SECONDS = int(os.getenv("WALK_INTERVAL_SECONDS", "1800"))
SNMP_TIMEOUT = float(os.getenv("SNMP_TIMEOUT", "3.0"))
SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "2"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9600"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_mac_address(data: str) -> str:
    """
    Convert any MAC address format to standard aa:bb:cc:dd:ee:ff format.
    Handles binary data, various delimiters, and LLDP chassis ID formats.
    """
    if not data:
        return data
    
    try:
        if isinstance(data, bytes):
            byte_data = data
        elif isinstance(data, str):
            byte_data = data.encode('latin-1')
        else:
            return data
        
        if len(byte_data) == 6:
            return ':'.join(f'{b:02x}' for b in byte_data)
        elif len(byte_data) == 7 and byte_data[0] == 0x04:
            return ':'.join(f'{b:02x}' for b in byte_data[1:])
        
        if isinstance(data, str) and any(c in data for c in [':', '-', '.']):
            clean = data.replace(':', '').replace('-', '').replace('.', '')
            if len(clean) == 12 and all(c in '0123456789abcdefABCDEF' for c in clean):
                return ':'.join(clean[i:i+2].lower() for i in range(0, 12, 2))
        
        return data
    except Exception:
        return data


def clean_snmp_data(data):
    """Recursively clean SNMP data by removing NULL bytes and other problematic characters."""
    if isinstance(data, dict):
        return {k: clean_snmp_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_snmp_data(item) for item in data]
    elif isinstance(data, str):
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', data)
    elif isinstance(data, bytes):
        try:
            return data.decode('utf-8', errors='ignore').replace('\x00', '')
        except:
            return str(data)
    else:
        return data

async def fetch_devices_with_mibs(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        inventory = resp.json()
        return [
            device for device in inventory
            if device.get("snmp_enabled") and (device.get("mib_ids") or device.get("mib_id"))
        ]
    except Exception as e:
        print(f"[MIB-WALKER] Error fetching devices: {e}", flush=True)
        return []


async def fetch_mib_content(client: httpx.AsyncClient, mib_id: int) -> Optional[str]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/mibs/{mib_id}", timeout=10.0)
        if resp.status_code == 200:
            mib_data = resp.json()
            return mib_data.get("content")
        return None
    except Exception as e:
        print(f"[MIB-WALKER] Error fetching MIB content for ID {mib_id}: {e}", flush=True)
        return None


def load_mib_for_resolution() -> Optional[view.MibViewController]:
    try:
        mib_builder = builder.MibBuilder()
        compiler.addMibCompiler(
            mib_builder,
            sources=['http://mibs.pysnmp.com/asn1/@mib@']
        )
        
        standard_mibs = [
            'SNMPv2-MIB', 'IF-MIB', 'IP-MIB', 'TCP-MIB', 'UDP-MIB',
            'HOST-RESOURCES-MIB', 'Printer-MIB', 'BRIDGE-MIB', 'ENTITY-MIB',
            'LLDP-MIB'
        ]
        
        loaded_count = 0
        for mib in standard_mibs:
            try:
                mib_builder.load_modules(mib)
                loaded_count += 1
            except Exception:
                pass
        
        print(f"[MIB-WALKER] Loaded {loaded_count}/{len(standard_mibs)} standard MIBs for OID resolution", flush=True)
        return view.MibViewController(mib_builder)
    except Exception as e:
        print(f"[MIB-WALKER] Error loading MIBs: {e}", flush=True)
        return None


def _get_text_label_from_oid(oid_str: str, mib_view: Optional[view.MibViewController]) -> str:
    if not mib_view:
        return _create_oid_label_fallback(oid_str)
    
    try:
        oid_tuple = tuple(int(x) for x in oid_str.split('.') if x)
        
        _, label, suffix = mib_view.getNodeName(oid_tuple)
        
        if label and len(label) > 0:
            text_name = label[-1]
            
            if suffix and len(suffix) > 0:
                suffix_str = '.'.join(str(x) for x in suffix)
                return f"{text_name}.{suffix_str}"
            else:
                return text_name
        
        return _create_oid_label_fallback(oid_str)
        
    except Exception:
        return _create_oid_label_fallback(oid_str)


def _create_oid_label_fallback(oid: str, base_oid: str = None) -> str:
    try:
        parts = oid.split('.')
        
        if base_oid:
            base_parts = base_oid.split('.')
            if len(parts) > len(base_parts):
                remaining = parts[len(base_parts):]
                if len(remaining) <= 4:
                    return '.'.join(remaining)
                else:
                    return '.'.join(remaining[-4:])
        
        if len(parts) >= 4:
            return '.'.join(parts[-4:])
        elif len(parts) >= 2:
            return '.'.join(parts[-2:])
        
        return oid
    except Exception:
        return oid


async def walk_oid_tree(ip: str, community: str, version: str, base_oid: str, mib_view: Optional[view.MibViewController] = None, max_results: int = 100) -> List[Tuple[str, str, str]]:
    try:
        snmpEngine = SnmpEngine()
        results = []
        mpModel = 0 if version == "1" else 1
        
        async for errorIndication, errorStatus, errorIndex, varBinds in walk_cmd(
            snmpEngine,
            CommunityData(community, mpModel=mpModel),
            await UdpTransportTarget.create((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False
        ):
            if errorIndication or errorStatus:
                break
            
            for varBind in varBinds:
                oid = str(varBind[0])
                raw_value = varBind[1]
                try:
                    if hasattr(raw_value, 'asNumbers'):
                        value = bytes(raw_value.asNumbers()).decode('latin-1')
                    elif hasattr(raw_value, 'prettyPrint'):
                        value = raw_value.prettyPrint()
                    else:
                        value = str(raw_value)
                except:
                    value = str(raw_value)
                
                if not oid.startswith(base_oid):
                    snmpEngine.close_dispatcher()
                    return results
                
                label = _get_text_label_from_oid(oid, mib_view)
                results.append((oid, value, label))
                
                if len(results) >= max_results:
                    snmpEngine.close_dispatcher()
                    return results
        
        snmpEngine.close_dispatcher()
        return results
        
    except Exception as e:
        print(f"[MIB-WALKER] Walk error for {ip} OID {base_oid}: {e}", flush=True)
        return []


async def get_single_oid(ip: str, community: str, version: str, oid: str) -> Optional[str]:
    try:
        snmpEngine = SnmpEngine()
        mpModel = 0 if version == "1" else 1
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmpEngine,
            CommunityData(community, mpModel=mpModel),
            await UdpTransportTarget.create((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        
        snmpEngine.close_dispatcher()
        
        if errorIndication or errorStatus:
            return None
        
        if varBinds:
            return str(varBinds[0][1])
        
        return None
        
    except Exception:
        return None


async def walk_interfaces(ip: str, community: str, version: str) -> Dict[str, Any]:
    interface_data = {}
    
    if_descr = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.2", max_results=50)
    if_type = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.3", max_results=50)
    if_speed = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.5", max_results=50)
    if_admin_status = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.7", max_results=50)
    if_oper_status = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.8", max_results=50)
    
    descr_map = {oid.split('.')[-1]: val for oid, val, _ in if_descr}
    type_map = {oid.split('.')[-1]: val for oid, val, _ in if_type}
    speed_map = {oid.split('.')[-1]: val for oid, val, _ in if_speed}
    admin_map = {oid.split('.')[-1]: val for oid, val, _ in if_admin_status}
    oper_map = {oid.split('.')[-1]: val for oid, val, _ in if_oper_status}
    
    for idx in descr_map.keys():
        interface_data[idx] = {
            "description": descr_map.get(idx, ""),
            "type": type_map.get(idx, ""),
            "speed": speed_map.get(idx, "0"),
            "admin_status": admin_map.get(idx, ""),
            "oper_status": oper_map.get(idx, "")
        }
    
    return interface_data


async def walk_system_info(ip: str, community: str, version: str) -> Dict[str, Any]:
    system_data = {}
    
    uptime = await get_single_oid(ip, community, version, "1.3.6.1.2.1.1.3.0")
    if uptime:
        system_data["uptime"] = uptime
    
    num_users = await get_single_oid(ip, community, version, "1.3.6.1.2.1.25.1.5.0")
    if num_users:
        system_data["num_users"] = num_users
    
    processes = await get_single_oid(ip, community, version, "1.3.6.1.2.1.25.1.6.0")
    if processes:
        system_data["num_processes"] = processes
    
    return system_data


async def walk_storage(ip: str, community: str, version: str) -> Dict[str, Any]:
    storage_data = {}
    
    hr_storage_descr = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.3", max_results=30)
    hr_storage_units = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.4", max_results=30)
    hr_storage_size = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.5", max_results=30)
    hr_storage_used = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.6", max_results=30)
    
    descr_map = {oid.split('.')[-1]: val for oid, val, _ in hr_storage_descr}
    units_map = {oid.split('.')[-1]: val for oid, val, _ in hr_storage_units}
    size_map = {oid.split('.')[-1]: val for oid, val, _ in hr_storage_size}
    used_map = {oid.split('.')[-1]: val for oid, val, _ in hr_storage_used}
    
    for idx in descr_map.keys():
        storage_data[idx] = {
            "description": descr_map.get(idx, ""),
            "units": units_map.get(idx, ""),
            "size": size_map.get(idx, "0"),
            "used": used_map.get(idx, "0")
        }
    
    return storage_data


async def walk_lldp_neighbors(ip: str, community: str, version: str) -> Dict[str, Any]:
    lldp_data = {
        "local_system": {},
        "neighbors": []
    }
    
    try:
        lldp_loc_chassis_id = await get_single_oid(ip, community, version, "1.0.8802.1.1.2.1.3.2.0")
        lldp_loc_sysname = await get_single_oid(ip, community, version, "1.0.8802.1.1.2.1.3.3.0")
        lldp_loc_sysdesc = await get_single_oid(ip, community, version, "1.0.8802.1.1.2.1.3.4.0")
        
        if lldp_loc_chassis_id:
            lldp_data["local_system"]["chassis_id"] = normalize_mac_address(lldp_loc_chassis_id)
        if lldp_loc_sysname:
            lldp_data["local_system"]["sysname"] = lldp_loc_sysname
        if lldp_loc_sysdesc:
            lldp_data["local_system"]["sysdesc"] = lldp_loc_sysdesc
        
        lldp_rem_chassis_id = await walk_oid_tree(ip, community, version, "1.0.8802.1.1.2.1.4.1.1.5", max_results=100)
        lldp_rem_port_id = await walk_oid_tree(ip, community, version, "1.0.8802.1.1.2.1.4.1.1.7", max_results=100)
        lldp_rem_port_desc = await walk_oid_tree(ip, community, version, "1.0.8802.1.1.2.1.4.1.1.8", max_results=100)
        lldp_rem_sysname = await walk_oid_tree(ip, community, version, "1.0.8802.1.1.2.1.4.1.1.9", max_results=100)
        lldp_rem_sysdesc = await walk_oid_tree(ip, community, version, "1.0.8802.1.1.2.1.4.1.1.10", max_results=100)
        
        neighbor_map = {}
        
        for oid, value, _ in lldp_rem_chassis_id:
            parts = oid.split('.')
            if len(parts) >= 3:
                local_port = parts[-2]
                rem_index = parts[-1]
                key = f"{local_port}.{rem_index}"
                if key not in neighbor_map:
                    neighbor_map[key] = {"local_port": local_port, "remote_index": rem_index}
                print(f"[DEBUG] Normalizing chassis ID: {repr(value)} -> {normalize_mac_address(value)}", flush=True)
                neighbor_map[key]["remote_chassis_id"] = normalize_mac_address(value)
        
        for oid, value, _ in lldp_rem_port_id:
            parts = oid.split('.')
            if len(parts) >= 3:
                local_port = parts[-2]
                rem_index = parts[-1]
                key = f"{local_port}.{rem_index}"
                if key not in neighbor_map:
                    neighbor_map[key] = {"local_port": local_port, "remote_index": rem_index}
                neighbor_map[key]["remote_port_id"] = value
        
        for oid, value, _ in lldp_rem_port_desc:
            parts = oid.split('.')
            if len(parts) >= 3:
                local_port = parts[-2]
                rem_index = parts[-1]
                key = f"{local_port}.{rem_index}"
                if key not in neighbor_map:
                    neighbor_map[key] = {"local_port": local_port, "remote_index": rem_index}
                neighbor_map[key]["remote_port_desc"] = value
        
        for oid, value, _ in lldp_rem_sysname:
            parts = oid.split('.')
            if len(parts) >= 3:
                local_port = parts[-2]
                rem_index = parts[-1]
                key = f"{local_port}.{rem_index}"
                if key not in neighbor_map:
                    neighbor_map[key] = {"local_port": local_port, "remote_index": rem_index}
                neighbor_map[key]["remote_sysname"] = value
        
        for oid, value, _ in lldp_rem_sysdesc:
            parts = oid.split('.')
            if len(parts) >= 3:
                local_port = parts[-2]
                rem_index = parts[-1]
                key = f"{local_port}.{rem_index}"
                if key not in neighbor_map:
                    neighbor_map[key] = {"local_port": local_port, "remote_index": rem_index}
                neighbor_map[key]["remote_sysdesc"] = value
        
        lldp_data["neighbors"] = list(neighbor_map.values())
        
        if lldp_data["neighbors"]:
            print(f"[MIB-WALKER] Found {len(lldp_data['neighbors'])} LLDP neighbors on {ip}", flush=True)
        
        return lldp_data
        
    except Exception as e:
        print(f"[MIB-WALKER] Error walking LLDP neighbors for {ip}: {e}", flush=True)
        return lldp_data


async def walk_stp_info(ip: str, community: str, version: str) -> Dict[str, Any]:
    stp_data = {
        "bridge_address": None,
        "priority": None,
        "designated_root": None,
        "root_cost": None,
        "root_port": None,
        "ports": {}
    }
    
    try:
        bridge_addr = await get_single_oid(ip, community, version, "1.3.6.1.2.1.17.1.1.0")
        if bridge_addr:
            stp_data["bridge_address"] = bridge_addr
        
        priority = await get_single_oid(ip, community, version, "1.3.6.1.2.1.17.2.2.0")
        if priority:
            stp_data["priority"] = priority
        
        designated_root = await get_single_oid(ip, community, version, "1.3.6.1.2.1.17.2.5.0")
        if designated_root:
            stp_data["designated_root"] = designated_root
        
        root_cost = await get_single_oid(ip, community, version, "1.3.6.1.2.1.17.2.6.0")
        if root_cost:
            stp_data["root_cost"] = root_cost
        
        root_port = await get_single_oid(ip, community, version, "1.3.6.1.2.1.17.2.7.0")
        if root_port:
            stp_data["root_port"] = root_port
        
        port_states = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.17.2.15.1.3", max_results=100)
        port_designated_roots = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.17.2.15.1.6", max_results=100)
        port_designated_bridges = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.17.2.15.1.8", max_results=100)
        
        port_map = {}
        
        for oid, value, _ in port_states:
            parts = oid.split('.')
            if len(parts) >= 1:
                port_idx = parts[-1]
                if port_idx not in port_map:
                    port_map[port_idx] = {"port": port_idx}
                state_val = value
                state_name = "unknown"
                if state_val == "1":
                    state_name = "disabled"
                elif state_val == "2":
                    state_name = "blocking"
                elif state_val == "3":
                    state_name = "listening"
                elif state_val == "4":
                    state_name = "learning"
                elif state_val == "5":
                    state_name = "forwarding"
                elif state_val == "6":
                    state_name = "broken"
                port_map[port_idx]["state"] = state_name
                port_map[port_idx]["state_value"] = state_val
        
        for oid, value, _ in port_designated_roots:
            parts = oid.split('.')
            if len(parts) >= 1:
                port_idx = parts[-1]
                if port_idx not in port_map:
                    port_map[port_idx] = {"port": port_idx}
                port_map[port_idx]["designated_root"] = value
        
        for oid, value, _ in port_designated_bridges:
            parts = oid.split('.')
            if len(parts) >= 1:
                port_idx = parts[-1]
                if port_idx not in port_map:
                    port_map[port_idx] = {"port": port_idx}
                port_map[port_idx]["designated_bridge"] = value
        
        stp_data["ports"] = port_map
        
        if port_map:
            print(f"[MIB-WALKER] Found STP info for {len(port_map)} ports on {ip}", flush=True)
        
        return stp_data
        
    except Exception as e:
        print(f"[MIB-WALKER] Error walking STP info for {ip}: {e}", flush=True)
        return stp_data


async def walk_device(client: httpx.AsyncClient, ip: str, community: str, version: str, mib_id: int, mib_name: str, oid_prefix: Optional[str] = None) -> Dict[str, Any]:
    print(f"[MIB-WALKER] Walking device {ip} with MIB {mib_name} (SNMP v{version})", flush=True)
    
    mib_data = {
        "walked_at": now_iso(),
        "mib_used": mib_name
    }
    
    try:
        interfaces = await walk_interfaces(ip, community, version)
        if interfaces:
            mib_data["interfaces"] = interfaces
            print(f"[MIB-WALKER] Found {len(interfaces)} interfaces on {ip}", flush=True)
        
        system_info = await walk_system_info(ip, community, version)
        if system_info:
            mib_data["system"] = system_info
        
        storage = await walk_storage(ip, community, version)
        if storage:
            mib_data["storage"] = storage
            print(f"[MIB-WALKER] Found {len(storage)} storage entries on {ip}", flush=True)
        
        lldp_neighbors = await walk_lldp_neighbors(ip, community, version)
        if lldp_neighbors and (lldp_neighbors.get("neighbors") or lldp_neighbors.get("local_system")):
            mib_data["lldp"] = lldp_neighbors
        
        stp_info = await walk_stp_info(ip, community, version)
        if stp_info and (stp_info.get("bridge_address") or stp_info.get("ports")):
            mib_data["stp"] = stp_info
        
        if oid_prefix:
            mib_view = load_mib_for_resolution()
            
            vendor_data = await walk_oid_tree(ip, community, version, oid_prefix, mib_view, max_results=500)
            if vendor_data:
                mib_data["VENDOR_MIB_DATA"] = {
                    label if label else oid: {"oid": oid, "value": value}
                    for oid, value, label in vendor_data
                }
                print(f"[MIB-WALKER] Found {len(vendor_data)} vendor-specific OIDs on {ip}", flush=True)
        
        return mib_data
        
    except Exception as e:
        print(f"[MIB-WALKER] Error walking {ip}: {e}", flush=True)
        return {}


async def update_device_mib_data(client: httpx.AsyncClient, ip: str, mib_data: Dict[str, Any]):
    try:
        current_resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip}", timeout=10.0)
        if current_resp.status_code != 200:
            print(f"[MIB-WALKER] Failed to fetch current data for {ip}", flush=True)
            return
        
        current = current_resp.json()
        existing_snmp_data = current.get("snmp_data", {})
        
        merged_data = {**existing_snmp_data, **mib_data}
        print(f"[MIB-WALKER] Cleaning SNMP data for {ip}", flush=True)
        cleaned_data = clean_snmp_data(merged_data)
        print(f"[MIB-WALKER] SNMP data cleaned for {ip}", flush=True)
        
        payload = {
            "snmp_data": cleaned_data,
            "last_probed": now_iso()
        }
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"[MIB-WALKER] Updated MIB data for {ip}", flush=True)
        else:
            print(f"[MIB-WALKER] Failed to update {ip}: {resp.status_code}", flush=True)
            
    except Exception as e:
        print(f"[MIB-WALKER] Error updating {ip}: {e}", flush=True)


async def test_mib_on_device(ip: str, community: str, version: str, mib_id: int, mib_name: str, oid_prefix: Optional[str]) -> Dict[str, Any]:
    score = 0
    error_count = 0
    oid_count = 0
    
    try:
        if oid_prefix:
            vendor_data = await walk_oid_tree(ip, community, version, oid_prefix, None, max_results=50)
            oid_count += len(vendor_data)
            
            non_empty_values = sum(1 for _, value, _ in vendor_data if value and value.strip() and value != "No Such Object currently exists at this OID")
            score += non_empty_values * 10
        
        system_desc = await get_single_oid(ip, community, version, "1.3.6.1.2.1.1.1.0")
        if system_desc:
            oid_count += 1
            score += 5
        
        return {
            "mib_id": mib_id,
            "mib_name": mib_name,
            "score": score,
            "oid_count": oid_count,
            "error_count": error_count,
            "success": score > 0
        }
    except Exception as e:
        return {
            "mib_id": mib_id,
            "mib_name": mib_name,
            "score": 0,
            "oid_count": 0,
            "error_count": 1,
            "success": False,
            "error": str(e)
        }


async def handle_test_mibs(request):
    from aiohttp import web
    import httpx
    
    try:
        data = await request.json()
        ip_address = data.get("ip_address")
        mib_ids = data.get("mib_ids", [])
        
        if not ip_address:
            return web.json_response({"error": "ip_address required"}, status=400)
        
        if not mib_ids:
            return web.json_response({"error": "mib_ids required"}, status=400)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip_address}")
            if resp.status_code != 200:
                return web.json_response({"error": f"Device {ip_address} not found"}, status=404)
            
            device = resp.json()
            ip = device.get("ip_address")
            community = device.get("snmp_community", "public")
            version = device.get("snmp_version", "2c")
            
            mibs_resp = await client.get(f"{STATE_SERVER_URL}/api/mibs")
            if mibs_resp.status_code != 200:
                return web.json_response({"error": "Could not fetch MIBs"}, status=500)
            
            all_mibs = mibs_resp.json()
            mib_lookup = {m["id"]: m for m in all_mibs}
            
            results = []
            for mib_id in mib_ids:
                mib = mib_lookup.get(mib_id)
                if not mib:
                    continue
                
                result = await test_mib_on_device(
                    ip, 
                    community, 
                    version, 
                    mib_id, 
                    mib["name"], 
                    mib.get("oid_prefix")
                )
                results.append(result)
                print(f"[MIB-WALKER] Tested {mib['name']} on {ip}: score={result['score']}", flush=True)
            
            results.sort(key=lambda x: x["score"], reverse=True)
            
            return web.json_response({
                "ip": ip,
                "results": results,
                "best_mib": results[0] if results else None
            })
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_walk_trigger(request):
    from aiohttp import web
    import httpx
    
    try:
        data = await request.json()
        ip_address = data.get("ip_address")
        
        if not ip_address:
            return web.json_response({"error": "ip_address required"}, status=400)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip_address}")
            if resp.status_code != 200:
                return web.json_response({"error": f"Device {ip_address} not found"}, status=404)
            
            device = resp.json()
            
            mib_ids = device.get("mib_ids") or ([device.get("mib_id")] if device.get("mib_id") else [])
            
            if not mib_ids:
                return web.json_response({"error": f"Device {ip_address} has no MIBs assigned"}, status=400)
            
            ip = device.get("ip_address")
            community = device.get("snmp_community", "public")
            version = device.get("snmp_version", "2c")
            
            mibs_resp = await client.get(f"{STATE_SERVER_URL}/api/mibs")
            if mibs_resp.status_code != 200:
                return web.json_response({"error": "Could not fetch MIBs"}, status=500)
                
            all_mibs = mibs_resp.json()
            mib_lookup = {m["id"]: m for m in all_mibs}
            
            combined_data = {
                "walked_at": now_iso(),
                "mib_results": {}
            }
            
            interfaces_combined = {}
            storage_combined = {}
            system_combined = {}
            lldp_data = None
            stp_data = None
            
            for mib_id in mib_ids:
                mib = mib_lookup.get(mib_id)
                if not mib:
                    continue
                    
                mib_name = mib["name"]
                oid_prefix = mib.get("oid_prefix")
                
                mib_data = await walk_device(client, ip, community, version, mib_id, mib_name, oid_prefix)
                if mib_data:
                    combined_data["mib_results"][mib_name] = mib_data
                    
                    if "interfaces" in mib_data:
                        interfaces_combined.update(mib_data["interfaces"])
                    if "storage" in mib_data:
                        storage_combined.update(mib_data["storage"])
                    if "system" in mib_data:
                        system_combined.update(mib_data["system"])
                    if "lldp" in mib_data and not lldp_data:
                        lldp_data = mib_data["lldp"]
                    if "stp" in mib_data and not stp_data:
                        stp_data = mib_data["stp"]
            
            if interfaces_combined:
                combined_data["interfaces"] = interfaces_combined
            if storage_combined:
                combined_data["storage"] = storage_combined
            if system_combined:
                combined_data["system"] = system_combined
            if lldp_data:
                combined_data["lldp"] = lldp_data
            if stp_data:
                combined_data["stp"] = stp_data
            
            if not combined_data.get("mib_results"):
                return web.json_response({"error": "MIB walk failed"}, status=500)
            
            await update_device_mib_data(client, ip, combined_data)
            
            return web.json_response({
                "status": "ok",
                "ip": ip,
                "mibs_walked": len(mib_ids),
                "walked_at": combined_data.get("walked_at")
            })
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "walk_interval": WALK_INTERVAL_SECONDS
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_post("/walk", handle_walk_trigger)
    app.router.add_post("/test-mibs", handle_test_mibs)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def walker_loop():
    print("[MIB-WALKER] DISABLED - MIB walker service is disabled. Exiting.", flush=True)
    stop_event.set()
    return


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        walker_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
