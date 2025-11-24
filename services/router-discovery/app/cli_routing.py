from dataclasses import dataclass
from typing import List, Optional

import paramiko


@dataclass
class CLIRouteEntry:
    destination: str
    prefix_length: int
    next_hop: Optional[str]
    protocol: Optional[str]


def _parse_route_line(line: str) -> Optional[CLIRouteEntry]:
    line = line.strip()
    if not line or line.startswith("Gateway of last resort"):
        return None

    # Expect lines like:
    #  S    10.65.8.0/22 [1/0] via 10.66.0.97
    #  C    10.120.0.0/16 is directly connected, GigabitEthernet0/0/0
    tokens = line.split()
    if len(tokens) < 2:
        return None

    proto_token = tokens[0]
    # Skip non-route header lines e.g. 'Codes:'
    if not proto_token[0].isalpha() or "/" not in tokens[1]:
        return None

    protocol_map = {
        "C": "connected",
        "S": "static",
        "O": "ospf",
        "D": "eigrp",
        "B": "bgp",
    }
    protocol = protocol_map.get(proto_token[0], proto_token[0])

    prefix = tokens[1]
    try:
        dest_str, plen_str = prefix.split("/")
        prefix_len = int(plen_str)
    except ValueError:
        return None

    next_hop: Optional[str] = None
    if "via" in tokens:
        try:
            via_index = tokens.index("via")
            if via_index + 1 < len(tokens):
                candidate = tokens[via_index + 1].rstrip(",")
                next_hop = candidate
        except ValueError:
            next_hop = None

    return CLIRouteEntry(
        destination=dest_str,
        prefix_length=prefix_len,
        next_hop=next_hop,
        protocol=protocol,
    )


def fetch_vrf_routes_via_ssh(
    host: str,
    username: str,
    password: str,
    vrf: Optional[str] = None,
    timeout: int = 10,
) -> List[CLIRouteEntry]:
    """Fetch IPv4 routes via SSH by running show ip route [vrf <name>]."""
    command = "show ip route vrf " + vrf if vrf else "show ip route"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, username=username, password=password, timeout=timeout)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        output = stdout.read().decode("utf-8", errors="ignore")
    finally:
        client.close()

    routes: List[CLIRouteEntry] = []
    for line in output.splitlines():
        entry = _parse_route_line(line)
        if entry is not None:
            routes.append(entry)

    return routes
