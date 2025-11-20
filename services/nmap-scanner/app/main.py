import asyncio
import os
import subprocess
import xml.etree.ElementTree as ET
import time
import signal
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "3600"))
SCAN_PROFILE = os.getenv("SCAN_PROFILE", "standard")
CUSTOM_NMAP_ARGS = os.getenv("CUSTOM_NMAP_ARGS", "")
NMAP_TIMING = os.getenv("NMAP_TIMING", "4")
NSE_SCRIPTS = os.getenv("NSE_SCRIPTS", "default,vulners,vulscan")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9200"))
TUNNEL_NETWORKS = os.getenv("TUNNEL_NETWORKS", "")
ENABLE_SUBNET_DISCOVERY = os.getenv("ENABLE_SUBNET_DISCOVERY", "true").lower() == "true"
MAX_PARALLEL_SCANS = int(os.getenv("MAX_PARALLEL_SCANS", "5"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_nmap_command(targets: List[str], scan_profile: str) -> List[str]:
    base_cmd = ["nmap", "-oX", "-", "-T", NMAP_TIMING, "--privileged"]
    
    if scan_profile == "quick":
        base_cmd.extend(["-F", "-sV", "--version-intensity", "2"])
    elif scan_profile == "standard":
        base_cmd.extend(["-p-", "-sV", "-O", "--osscan-guess", "--version-intensity", "5"])
        if NSE_SCRIPTS:
            base_cmd.extend(["--script", NSE_SCRIPTS])
    elif scan_profile == "aggressive":
        base_cmd.extend(["-A", "-p-", "-T5"])
        if NSE_SCRIPTS:
            base_cmd.extend(["--script", NSE_SCRIPTS])
    elif scan_profile == "stealth":
        base_cmd.extend(["-sS", "-p-", "-sV", "-O", "--osscan-guess"])
    elif scan_profile == "full":
        base_cmd.extend(["-A", "-p-", "-sC", "-sV", "-O", "--osscan-guess", "--version-all"])
        if NSE_SCRIPTS:
            base_cmd.extend(["--script", NSE_SCRIPTS])
    
    if CUSTOM_NMAP_ARGS:
        base_cmd.extend(CUSTOM_NMAP_ARGS.split())
    
    base_cmd.extend(targets)
    
    return base_cmd


async def run_nmap_scan(targets: List[str], scan_profile: str) -> Optional[str]:
    if not targets:
        return None
    
    cmd = get_nmap_command(targets, scan_profile)
    
    print(f"[NMAP] Running: {" ".join(cmd)}", flush=True)
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return stdout.decode('utf-8', errors='ignore')
        else:
            print(f"[NMAP] Error: {stderr.decode('utf-8', errors='ignore')}", flush=True)
            return None
    except Exception as e:
        print(f"[NMAP] Exception running nmap: {e}", flush=True)
        return None


def parse_nmap_xml(xml_output: str) -> List[Dict]:
    results = []
    
    try:
        root = ET.fromstring(xml_output)
        
        for host in root.findall('.//host'):
            status_elem = host.find('status')
            if status_elem is None or status_elem.get('state') != 'up':
                continue
            
            host_data = {
                "status": "active",
                "last_probed": now_iso(),
                "nmap_scan_time": now_iso()
            }
            
            address_elem = host.find('address[@addrtype="ipv4"]')
            if address_elem is not None:
                host_data["ip_address"] = address_elem.get('addr')
            else:
                continue
            
            mac_elem = host.find('address[@addrtype="mac"]')
            if mac_elem is not None:
                host_data["mac_address"] = mac_elem.get('addr')
                vendor = mac_elem.get('vendor')
                if vendor:
                    host_data["vendor"] = vendor
            
            hostnames_elem = host.find('hostnames')
            if hostnames_elem is not None:
                hostname_list = []
                for hostname in hostnames_elem.findall('hostname'):
                    name = hostname.get('name')
                    if name:
                        hostname_list.append(name)
                if hostname_list:
                    host_data["hostname"] = hostname_list[0]
                    host_data["all_hostnames"] = hostname_list
            
            os_elem = host.find('os')
            if os_elem is not None:
                os_matches = []
                for osmatch in os_elem.findall('osmatch'):
                    os_matches.append({
                        "name": osmatch.get('name'),
                        "accuracy": osmatch.get('accuracy'),
                        "osclass": []
                    })
                    for osclass in osmatch.findall('osclass'):
                        os_matches[-1]["osclass"].append({
                            "type": osclass.get('type'),
                            "vendor": osclass.get('vendor'),
                            "osfamily": osclass.get('osfamily'),
                            "osgen": osclass.get('osgen'),
                            "accuracy": osclass.get('accuracy')
                        })
                
                if os_matches:
                    host_data["os_detection"] = os_matches
                    host_data["os_name"] = os_matches[0]["name"]
                    host_data["os_accuracy"] = os_matches[0]["accuracy"]
            
            uptime_elem = host.find('uptime')
            if uptime_elem is not None:
                host_data["uptime_seconds"] = uptime_elem.get('seconds')
            
            ports_elem = host.find('ports')
            open_ports = {}
            
            if ports_elem is not None:
                for port in ports_elem.findall('port'):
                    state = port.find('state')
                    if state is not None and state.get('state') == 'open':
                        port_id = port.get('portid')
                        protocol = port.get('protocol')
                        
                        port_info = {
                            "protocol": protocol,
                            "state": "open"
                        }
                        
                        service = port.find('service')
                        if service is not None:
                            port_info["service"] = service.get('name', 'unknown')
                            port_info["product"] = service.get('product', '')
                            port_info["version"] = service.get('version', '')
                            port_info["extrainfo"] = service.get('extrainfo', '')
                            port_info["ostype"] = service.get('ostype', '')
                            port_info["method"] = service.get('method', '')
                            port_info["conf"] = service.get('conf', '')
                            
                            cpes = []
                            for cpe in service.findall('cpe'):
                                cpes.append(cpe.text)
                            if cpes:
                                port_info["cpe"] = cpes
                        
                        script_results = []
                        for script in port.findall('script'):
                            script_results.append({
                                "id": script.get('id'),
                                "output": script.get('output')
                            })
                        if script_results:
                            port_info["scripts"] = script_results
                        
                        open_ports[port_id] = port_info
            
            if open_ports:
                host_data["open_ports"] = open_ports
            
            host_scripts = []
            hostscript = host.find('hostscript')
            if hostscript is not None:
                for script in hostscript.findall('script'):
                    host_scripts.append({
                        "id": script.get('id'),
                        "output": script.get('output')
                    })
            if host_scripts:
                host_data["host_scripts"] = host_scripts
            
            results.append(host_data)
    
    except Exception as e:
        print(f"[NMAP] Error parsing XML: {e}", flush=True)
    
    return results


async def discover_subnet(network: str) -> List[str]:
    print(f"[NMAP] Discovering live hosts in {network}", flush=True)
    
    cmd = ["nmap", "-sn", "-T4", "--privileged", network, "-oX", "-"]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"[NMAP] Discovery error: {stderr.decode('utf-8', errors='ignore')}", flush=True)
            return []
        
        xml_output = stdout.decode('utf-8', errors='ignore')
        root = ET.fromstring(xml_output)
        
        live_hosts = []
        for host in root.findall('.//host'):
            status_elem = host.find('status')
            if status_elem is not None and status_elem.get('state') == 'up':
                address_elem = host.find('address[@addrtype="ipv4"]')
                if address_elem is not None:
                    ip = address_elem.get('addr')
                    live_hosts.append(ip)
        
        print(f"[NMAP] Found {len(live_hosts)} live hosts in {network}", flush=True)
        return live_hosts
    
    except Exception as e:
        print(f"[NMAP] Exception discovering subnet {network}: {e}", flush=True)
        return []


async def fetch_inventory(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[NMAP] Error fetching inventory: {e}", flush=True)
        return []


async def fetch_discovered_networks(client: httpx.AsyncClient) -> List[str]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/networks/discovered", timeout=10.0)
        resp.raise_for_status()
        networks = resp.json()
        return [n["network"] for n in networks]
    except Exception as e:
        print(f"[NMAP] Error fetching discovered networks: {e}", flush=True)
        return []


async def update_device(client: httpx.AsyncClient, ip: str, data: Dict):
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip}", timeout=5.0)
        
        if resp.status_code == 404:
            resp = await client.post(f"{STATE_SERVER_URL}/api/inventory", json=data, timeout=10.0)
            if resp.status_code < 300:
                print(f"[NMAP] Created new device: {ip}", flush=True)
            else:
                print(f"[NMAP] Failed to create {ip}: {resp.status_code}", flush=True)
        elif resp.status_code == 200:
            resp = await client.put(f"{STATE_SERVER_URL}/api/inventory/{ip}", json=data, timeout=10.0)
            if resp.status_code < 300:
                ports_count = len(data.get("open_ports", {}))
                os_name = data.get("os_name", "unknown")
                print(f"[NMAP] Updated {ip}: {ports_count} ports, OS: {os_name}", flush=True)
            else:
                print(f"[NMAP] Failed to update {ip}: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[NMAP] Error updating {ip}: {e}", flush=True)


async def scan_network(client: httpx.AsyncClient, network: str, scan_profile: str):
    """Scan a single network and update devices"""
    print(f"[NMAP] Starting scan of network: {network}", flush=True)
    
    try:
        if ENABLE_SUBNET_DISCOVERY:
            discovered_hosts = await discover_subnet(network)
        else:
            discovered_hosts = [network]
        
        if not discovered_hosts:
            print(f"[NMAP] No hosts found in {network}", flush=True)
            return
        
        batch_size = 50
        for i in range(0, len(discovered_hosts), batch_size):
            if stop_event.is_set():
                break
            
            batch = discovered_hosts[i:i+batch_size]
            xml_output = await run_nmap_scan(batch, scan_profile)
            
            if xml_output:
                results = parse_nmap_xml(xml_output)
                
                for result in results:
                    ip = result.get("ip_address")
                    if ip:
                        await update_device(client, ip, result)
        
        print(f"[NMAP] Completed scan of network: {network}", flush=True)
    except Exception as e:
        print(f"[NMAP] Error scanning network {network}: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "scan_interval": SCAN_INTERVAL_SECONDS,
            "scan_profile": SCAN_PROFILE,
            "nmap_timing": NMAP_TIMING,
            "nse_scripts": NSE_SCRIPTS,
            "subnet_discovery": ENABLE_SUBNET_DISCOVERY,
            "max_parallel_scans": MAX_PARALLEL_SCANS
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def scan_loop():
    print(f"[NMAP] DISABLED - NMAP scanner service is disabled. Exiting.", flush=True)
    stop_event.set()
    return


async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        scan_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
