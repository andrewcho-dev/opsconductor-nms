"""
Secondary-Level Switch Detection Module

This module implements probabilistic switch detection using packet analysis.
It runs separately from primary discovery logic and can be easily removed if needed.

Detection is based on:
- Layer 2 control protocols (STP/RSTP/MSTP, LLDP, CDP)
- VLAN behavior patterns
- Vendor OUI classification
- Control-plane vs user-plane traffic ratios
- Multi-source behavior analysis

Author: AI-assisted network topology discovery
Status: Experimental - Secondary detection layer
"""

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple


OUI_NETWORK_VENDORS = {
    "00:00:0c", "00:01:42", "00:01:43", "00:01:63", "00:01:64", "00:01:96", "00:01:97", "00:01:c7",
    "00:04:96", "00:05:73", "00:09:43", "00:0a:41", "00:0a:f7", "00:0d:bc", "00:0d:bd", "00:0d:ec",
    "00:0e:38", "00:0e:83", "00:0f:23", "00:0f:24", "00:10:0d", "00:10:11", "00:10:1f", "00:10:79",
    "00:10:7b", "00:10:db", "00:11:20", "00:11:21", "00:11:5c", "00:11:85", "00:11:92", "00:11:93",
    "00:11:bb", "00:12:00", "00:12:01", "00:12:17", "00:12:43", "00:12:44", "00:12:7f", "00:12:80",
    "00:12:d9", "00:12:da", "00:13:19", "00:13:1a", "00:13:5f", "00:13:60", "00:13:7f", "00:13:80",
    "00:13:c3", "00:13:c4", "00:14:1b", "00:14:1c", "00:14:69", "00:14:6a", "00:14:a8", "00:14:a9",
    "00:14:bf", "00:14:f1", "00:14:f2", "00:15:2b", "00:15:2c", "00:15:62", "00:15:63", "00:15:c6",
    "00:15:c7", "00:15:f9", "00:16:46", "00:16:47", "00:16:9c", "00:16:9d", "00:16:c7", "00:16:c8",
    "00:17:0e", "00:17:0f", "00:17:3b", "00:17:59", "00:17:5a", "00:17:94", "00:17:95", "00:17:df",
    "00:18:0a", "00:18:18", "00:18:19", "00:18:73", "00:18:74", "00:18:b9", "00:18:ba", "00:19:06",
    "00:19:2f", "00:19:30", "00:19:55", "00:19:56", "00:19:a9", "00:19:aa", "00:19:e7", "00:19:e8",
    "00:1a:2f", "00:1a:30", "00:1a:6c", "00:1a:6d", "00:1a:a1", "00:1a:a2", "00:1a:e2", "00:1a:e3",
    "00:1b:0c", "00:1b:0d", "00:1b:2a", "00:1b:2b", "00:1b:53", "00:1b:54", "00:1b:67", "00:1b:8f",
    "00:1b:90", "00:1b:d4", "00:1b:d5", "00:1b:d7", "00:1c:0e", "00:1c:0f", "00:1c:10", "00:1c:57",
    "00:1c:58", "00:1c:b0", "00:1c:b1", "00:1c:f6", "00:1c:f9", "00:1d:45", "00:1d:46", "00:1d:70",
    "00:1d:71", "00:1d:a1", "00:1d:a2", "00:1d:e5", "00:1d:e6", "00:1e:13", "00:1e:14", "00:1e:49",
    "00:1e:4a", "00:1e:79", "00:1e:7a", "00:1e:bd", "00:1e:be", "00:1e:f6", "00:1e:f7", "00:1f:27",
    "00:1f:28", "00:1f:6c", "00:1f:6d", "00:1f:9d", "00:1f:9e", "00:1f:c9", "00:1f:ca", "00:21:1b",
    "00:21:1c", "00:21:55", "00:21:56", "00:21:a0", "00:21:a1", "00:21:d7", "00:21:d8", "00:22:0c",
    "00:22:55", "00:22:56", "00:22:90", "00:22:91", "00:22:bd", "00:22:be", "00:23:04", "00:23:05",
    "00:23:33", "00:23:34", "00:23:5d", "00:23:5e", "00:23:ab", "00:23:ac", "00:23:ea", "00:23:eb",
    "00:24:13", "00:24:14", "00:24:50", "00:24:51", "00:24:97", "00:24:98", "00:24:c3", "00:24:c4",
    "00:24:f7", "00:24:f9", "00:25:2e", "00:25:45", "00:25:46", "00:25:83", "00:25:84", "00:25:b4",
    "00:25:b5", "00:26:0a", "00:26:0b", "00:26:51", "00:26:52", "00:26:98", "00:26:99", "00:26:ca",
    "00:26:cb", "00:27:0c", "00:27:0d", "00:50:73", "00:60:2f", "00:60:3e", "00:60:47", "00:60:5c",
    "00:60:70", "00:60:83", "00:80:24", "00:90:21", "00:90:27", "00:90:69", "00:90:92", "00:90:ab",
    "00:90:bf", "00:90:d9", "00:a2:ee", "00:b0:64", "00:d0:06", "00:d0:58", "00:d0:59", "00:d0:79",
    "00:d0:90", "00:d0:97", "00:d0:ba", "00:d0:bb", "00:d0:bc", "00:d0:d3", "00:d0:e4", "00:d0:ff",
    "00:e0:14", "00:e0:1e", "00:e0:34", "00:e0:4f", "00:e0:52", "00:e0:8f", "00:e0:a3", "00:e0:b0",
    "00:e0:f7", "00:e0:f9", "00:e0:fe", "04:c5:a4", "08:00:20", "08:00:2b", "10:00:5a", "28:c0:da",
    "3c:df:1e", "40:55:39", "44:d3:ca", "4c:00:82", "50:06:04", "50:57:a8", "54:75:d0", "54:a2:74",
    "58:ac:78", "5c:50:15", "5c:83:8f", "64:00:f1", "64:9e:f3", "68:bc:0c", "6c:20:56", "6c:41:6a",
    "70:10:5c", "74:26:ac", "78:ba:f9", "7c:69:f6", "80:2a:a8", "84:78:ac", "84:b8:02", "88:75:56",
    "8c:60:4f", "90:e2:ba", "94:d4:69", "98:fc:11", "9c:37:f4", "a0:3d:6f", "a0:f8:49", "a4:4c:11",
    "a4:93:4c", "a8:0c:0d", "b0:aa:77", "b4:a4:e3", "b8:be:bf", "bc:67:1c", "c0:62:6b", "c4:64:13",
    "c8:00:84", "c8:f9:f9", "cc:d5:39", "cc:ef:48", "d0:72:dc", "d4:a0:2a", "d8:b1:90", "dc:7b:94",
    "e0:89:9d", "e4:c7:22", "e8:04:62", "e8:ba:70", "ec:44:76", "f0:9e:63", "f4:4e:05", "f8:66:f2",
    "fc:5b:39", "fc:99:47",
}

CONTROL_PROTOCOLS = {
    "arp", "lldp", "cdp", "stp", "rstp", "mstp", "lacp", "eapol", "igmp", "mld", "dhcp", "dns"
}


class DeviceFeatures:
    def __init__(self, mac: str):
        self.mac = mac
        self.stp_sender = False
        self.lldp_sender = False
        self.lldp_cap_bridge = False
        self.lldp_cap_router = False
        self.cdp_sender = False
        self.cdp_cap_bridge = False
        self.num_vlans_src: Set[int] = set()
        self.vendor_is_infra = False
        self.pct_control_plane_src = 0.0
        self.num_downstream_macs: Set[str] = set()
        self.control_plane_packets = 0
        self.total_packets = 0
        self.first_seen: Optional[str] = None
        self.last_seen: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "mac": self.mac,
            "stp_sender": self.stp_sender,
            "lldp_sender": self.lldp_sender,
            "lldp_cap_bridge": self.lldp_cap_bridge,
            "lldp_cap_router": self.lldp_cap_router,
            "cdp_sender": self.cdp_sender,
            "cdp_cap_bridge": self.cdp_cap_bridge,
            "num_vlans_src": len(self.num_vlans_src),
            "vendor_is_infra": self.vendor_is_infra,
            "pct_control_plane_src": self.pct_control_plane_src,
            "num_downstream_macs": len(self.num_downstream_macs),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class SwitchDetector:
    def __init__(self):
        self.device_features: Dict[str, DeviceFeatures] = {}
        self.packet_buffer: List[Dict] = []
        self.last_analysis_time: Optional[datetime] = None

    def add_packet(self, pkt_data: Dict) -> None:
        self.packet_buffer.append(pkt_data)
        if len(self.packet_buffer) > 50000:
            self.packet_buffer = self.packet_buffer[-25000:]

    def analyze_packets(self) -> Dict[str, Dict]:
        from scapy.all import Ether, Dot1Q, Packet as ScapyPacket
        
        results = {}
        self.last_analysis_time = datetime.now(timezone.utc)
        
        for mac in self.device_features.keys():
            features = self.device_features[mac]
            if features.total_packets > 0:
                features.pct_control_plane_src = features.control_plane_packets / features.total_packets
            
            score = self._calculate_switch_score(features)
            classification = self._classify_switch_probability(score)
            evidence = self._collect_evidence(features)
            
            results[mac] = {
                "mac": mac,
                "score": score,
                "classification": classification,
                "evidence": evidence,
                "features": features.to_dict(),
            }
        
        return results

    def process_raw_packet(self, pkt) -> None:
        from scapy.all import Ether, Dot1Q, ARP, Raw
        
        try:
            if not pkt.haslayer(Ether):
                return
            
            src_mac = pkt[Ether].src.lower()
            timestamp = datetime.now(timezone.utc).isoformat()
            
            if src_mac not in self.device_features:
                self.device_features[src_mac] = DeviceFeatures(src_mac)
            
            features = self.device_features[src_mac]
            features.total_packets += 1
            if features.first_seen is None:
                features.first_seen = timestamp
            features.last_seen = timestamp
            
            oui = self._extract_oui(src_mac)
            if oui in OUI_NETWORK_VENDORS:
                features.vendor_is_infra = True
            
            if pkt.haslayer(Dot1Q):
                vlan_id = pkt[Dot1Q].vlan
                features.num_vlans_src.add(vlan_id)
            
            self._detect_control_protocols(pkt, features)
            
        except Exception:
            pass

    def _extract_oui(self, mac: str) -> str:
        parts = mac.split(":")
        if len(parts) >= 3:
            return ":".join(parts[:3])
        return ""

    def _detect_control_protocols(self, pkt, features: DeviceFeatures) -> None:
        from scapy.all import Ether, LLC, SNAP, Raw
        
        try:
            ethertype = pkt[Ether].type if pkt.haslayer(Ether) else 0
            dst_mac = pkt[Ether].dst.lower() if pkt.haslayer(Ether) else ""
            
            if ethertype == 0x88cc:
                features.lldp_sender = True
                features.control_plane_packets += 1
                self._parse_lldp(pkt, features)
            
            elif dst_mac == "01:00:0c:cc:cc:cc":
                features.cdp_sender = True
                features.control_plane_packets += 1
                self._parse_cdp(pkt, features)
            
            elif dst_mac.startswith("01:80:c2:00:00:0") or ethertype == 0x0026:
                features.stp_sender = True
                features.control_plane_packets += 1
            
            elif pkt.haslayer(LLC):
                llc = pkt[LLC]
                if llc.dsap == 0x42 and llc.ssap == 0x42:
                    features.stp_sender = True
                    features.control_plane_packets += 1
            
        except Exception:
            pass

    def _parse_lldp(self, pkt, features: DeviceFeatures) -> None:
        try:
            from scapy.all import Raw
            if pkt.haslayer(Raw):
                raw_data = bytes(pkt[Raw].load)
                if b'\x00\x04' in raw_data or b'\x00\x08' in raw_data:
                    features.lldp_cap_bridge = True
                if b'\x00\x10' in raw_data:
                    features.lldp_cap_router = True
        except Exception:
            pass

    def _parse_cdp(self, pkt, features: DeviceFeatures) -> None:
        try:
            from scapy.all import Raw
            if pkt.haslayer(Raw):
                raw_data = bytes(pkt[Raw].load)
                if b'Switch' in raw_data or b'switch' in raw_data or b'Bridge' in raw_data:
                    features.cdp_cap_bridge = True
        except Exception:
            pass

    def _calculate_switch_score(self, features: DeviceFeatures) -> float:
        score = 0.0
        
        if features.stp_sender:
            score += 0.35
        
        if features.lldp_sender and features.lldp_cap_bridge:
            score += 0.35
        elif features.lldp_sender:
            score += 0.15
        
        if features.cdp_sender and features.cdp_cap_bridge:
            score += 0.30
        elif features.cdp_sender:
            score += 0.10
        
        if len(features.num_vlans_src) >= 5:
            score += 0.15
        elif len(features.num_vlans_src) >= 3:
            score += 0.08
        
        if features.vendor_is_infra:
            score += 0.10
        
        if features.pct_control_plane_src > 0.3:
            score += 0.10
        elif features.pct_control_plane_src > 0.15:
            score += 0.05
        
        if len(features.num_downstream_macs) >= 20:
            score += 0.15
        elif len(features.num_downstream_macs) >= 10:
            score += 0.08
        
        return min(1.0, score)

    def _classify_switch_probability(self, score: float) -> str:
        if score >= 0.8:
            return "almost_certainly_switch"
        elif score >= 0.6:
            return "likely_switch"
        elif score >= 0.35:
            return "possible_switch"
        elif score >= 0.15:
            return "unlikely_switch"
        else:
            return "not_switch"

    def _collect_evidence(self, features: DeviceFeatures) -> List[str]:
        evidence = []
        
        if features.stp_sender:
            evidence.append("Sends STP/RSTP BPDUs (strong switch indicator)")
        if features.lldp_sender:
            if features.lldp_cap_bridge:
                evidence.append("LLDP advertises bridge capability (strong switch indicator)")
            else:
                evidence.append("Sends LLDP frames")
        if features.cdp_sender:
            if features.cdp_cap_bridge:
                evidence.append("CDP advertises switch/bridge capability")
            else:
                evidence.append("Sends CDP frames (Cisco device)")
        if len(features.num_vlans_src) >= 3:
            evidence.append(f"Traffic observed in {len(features.num_vlans_src)} VLANs")
        if features.vendor_is_infra:
            evidence.append(f"Network infrastructure vendor OUI ({self._extract_oui(features.mac)})")
        if features.pct_control_plane_src > 0.15:
            evidence.append(f"High control-plane traffic ratio ({features.pct_control_plane_src:.1%})")
        if len(features.num_downstream_macs) >= 10:
            evidence.append(f"Appears upstream of {len(features.num_downstream_macs)} MACs")
        
        return evidence

    def get_switch_candidates(self, min_score: float = 0.35) -> Dict[str, Dict]:
        results = self.analyze_packets()
        return {
            mac: data
            for mac, data in results.items()
            if data["score"] >= min_score
        }

    def clear_old_data(self, max_age_seconds: int = 3600) -> None:
        now = datetime.now(timezone.utc)
        to_remove = []
        
        for mac, features in self.device_features.items():
            if features.last_seen:
                try:
                    last_seen = datetime.fromisoformat(features.last_seen.replace("Z", "+00:00"))
                    age = (now - last_seen).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(mac)
                except Exception:
                    pass
        
        for mac in to_remove:
            del self.device_features[mac]
