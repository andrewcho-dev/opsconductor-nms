"""
Simple SNMP implementation that avoids pysnmp compatibility issues.
Uses subprocess to call snmpwalk/snmpget commands for basic operations.
"""

import subprocess
import logging
import re
from typing import List, Optional
from .types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class SimpleSnmpClient:
    """Simple SNMP client using system snmp commands."""
    
    def __init__(self, timeout: int = 5, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
    
    def _run_snmp_command(self, command: List[str]) -> Optional[str]:
        """Run SNMP command and return output."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"SNMP command failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning("SNMP command timed out")
            return None
        except Exception as e:
            logger.error(f"SNMP command error: {e}")
            return None
    
    def get_system_info(self, ip: str, community: str) -> Optional[SystemInfo]:
        """Get system info via SNMP."""
        try:
            # Get system description using numeric OID
            cmd = ['snmpget', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.1.1.0']
            output = self._run_snmp_command(cmd)
            if not output:
                return None
            
            sys_descr = output.split(':')[-1].strip().strip('"')
            
            # Get system name using numeric OID
            cmd = ['snmpget', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.1.5.0']
            output = self._run_snmp_command(cmd)
            hostname = None
            if output and 'No Such Object' not in output:
                hostname = output.split(':')[-1].strip().strip('"')
            
            return SystemInfo(hostname=hostname, sys_descr=sys_descr, sys_object_id=None)
            
        except Exception as e:
            logger.error(f"Failed to get system info from {ip}: {e}")
            return None
    
    def get_routes(self, ip: str, community: str) -> List[RouteEntry]:
        """Get routing table via SNMP."""
        routes = []
        
        try:
            # Get routing table destinations
            dest_cmd = ['snmpwalk', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.4.21.1.1']
            dest_output = self._run_snmp_command(dest_cmd)
            
            # Get routing table netmasks
            mask_cmd = ['snmpwalk', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.4.21.1.11']
            mask_output = self._run_snmp_command(mask_cmd)
            
            if dest_output and mask_output:
                # Parse destinations and netmasks
                dest_routes = self._parse_snmp_routes(dest_output)
                mask_routes = self._parse_snmp_masks(mask_output)
                
                # Combine destinations with their netmasks
                for dest_ip in dest_routes:
                    if self._is_valid_route_ip(dest_ip, ip):
                        netmask = mask_routes.get(dest_ip, "255.255.255.0")  # Default to /24 if not found
                        cidr_notation = self._ip_and_mask_to_cidr(dest_ip, netmask)
                        
                        routes.append(RouteEntry(
                            destination=dest_ip,
                            netmask=netmask,
                            next_hop="0.0.0.0",
                            protocol='snmp'
                        ))
                        logger.debug(f"Added valid route: {dest_ip}/{netmask}")
            
            # Always add the local connected route for the device itself
            local_network = self._get_local_network(ip)
            routes.append(RouteEntry(
                destination=local_network,
                netmask="255.255.255.0",
                next_hop="0.0.0.0",
                protocol='connected'
            ))
            
            logger.info(f"Added {len(routes)} routes for {ip}")
            return routes
            
        except Exception as e:
            logger.error(f"Failed to get routes from {ip}: {e}")
            # Fallback to basic connected route
            local_network = self._get_local_network(ip)
            routes.append(RouteEntry(
                destination=local_network,
                netmask="255.255.255.0", 
                next_hop="0.0.0.0",
                protocol='connected'
            ))
            return routes
    
    def _parse_snmp_routes(self, output: str) -> List[str]:
        """Parse destination IPs from SNMP route output."""
        routes = []
        for line in output.splitlines():
            line = line.strip()
            if 'IpAddress:' in line:
                try:
                    ip_match = re.search(r'IpAddress: (\d+\.\d+\.\d+\.\d+)', line)
                    if ip_match:
                        dest_ip = ip_match.group(1)
                        routes.append(dest_ip)
                except Exception as e:
                    logger.debug(f"Failed to parse route line: {line}, error: {e}")
                    continue
        return routes
    
    def _parse_snmp_masks(self, output: str) -> dict:
        """Parse netmask mapping from SNMP mask output."""
        masks = {}
        for line in output.splitlines():
            line = line.strip()
            if 'IpAddress:' in line:
                try:
                    # Extract the IP from the OID (part before =)
                    oid_part = line.split('=')[0].strip()
                    # Extract the IP from the OID (last 4 octets)
                    oid_parts = oid_part.split('.')
                    if len(oid_parts) >= 4:
                        dest_ip = f"{oid_parts[-4]}.{oid_parts[-3]}.{oid_parts[-2]}.{oid_parts[-1]}"
                        
                        # Extract the netmask from the value
                        mask_match = re.search(r'IpAddress: (\d+\.\d+\.\d+\.\d+)', line)
                        if mask_match:
                            netmask = mask_match.group(1)
                            masks[dest_ip] = netmask
                except Exception as e:
                    logger.debug(f"Failed to parse mask line: {line}, error: {e}")
                    continue
        return masks
    
    def _ip_and_mask_to_cidr(self, ip: str, netmask: str) -> str:
        """Convert IP and netmask to CIDR notation."""
        try:
            # Convert netmask to CIDR prefix length
            mask_parts = netmask.split('.')
            prefix_length = 0
            for part in mask_parts:
                octet = int(part)
                while octet > 0:
                    prefix_length += octet & 1
                    octet >>= 1
            return f"{ip}/{prefix_length}"
        except Exception:
            return f"{ip}/24"  # Fallback
    
    def _is_valid_route_ip(self, dest_ip: str, device_ip: str) -> bool:
        """Validate that a route IP is legitimate for this network."""
        try:
            parts = dest_ip.split('.')
            if len(parts) != 4:
                return False
            
            # Convert to integers for validation
            octets = [int(part) for part in parts]
            
            # STRICT FILTERING - Absolutely no 1.x.x.x addresses
            if octets[0] == 1:  # NEVER accept 1.x.x.x - these are garbage
                return False
            
            # Filter out other invalid IPs
            if octets[0] == 0 and dest_ip != "0.0.0.0":
                return False
            if octets[0] == 255 and dest_ip != "255.255.255.255":
                return False
            if octets[0] >= 224:  # Multicast and above
                return False
            if octets[0] == 127 and dest_ip != "127.0.0.1":  # Loopback
                return False
            
            # ONLY accept IPs that are in your known network ranges
            # Your networks are: 10.120.x.x, 10.121.x.x, 10.66.x.x, etc.
            # Also allow 0.0.0.0 for default routes
            if octets[0] == 10:
                # Accept 10.x.x.x addresses
                return True
            elif dest_ip == "0.0.0.0":
                # Accept default route
                return True
            else:
                # REJECT everything else (including 1.x.x.x)
                return False
            
        except Exception:
            return False
    
    def _get_local_network(self, ip: str) -> str:
        """Get the local network for this device IP."""
        try:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            return f"{ip}/24"
        except Exception:
            return f"{ip}/24"
    
    def _get_route_mask(self, ip: str, community: str, dest_ip: str) -> Optional[str]:
        """Get netmask for a specific route."""
        try:
            cmd = ['snmpget', '-v2c', '-c', community, ip, f'IP-FORWARD-MIB::ipCidrRouteMask.{dest_ip.replace(".", ".")}.0.0.0.0.0']
            output = self._run_snmp_command(cmd)
            if output:
                mask = output.split(':')[-1].strip()
                return mask
        except:
            pass
        return None
    
    def _get_route_next_hop(self, ip: str, community: str, dest_ip: str) -> Optional[str]:
        """Get next hop for a specific route."""
        try:
            cmd = ['snmpget', '-v2c', '-c', community, ip, f'IP-FORWARD-MIB::ipCidrRouteNextHop.{dest_ip.replace(".", ".")}.0.0.0.0.0']
            output = self._run_snmp_command(cmd)
            if output:
                next_hop = output.split(':')[-1].strip()
                if next_hop and next_hop != '0.0.0.0':
                    return next_hop
        except:
            pass
        return None
    
    def get_interfaces(self, ip: str, community: str) -> List[dict]:
        """Get interface information via SNMP."""
        interfaces = []
        
        try:
            # Get IP addresses using numeric OID
            cmd = ['snmpwalk', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.4.20.1.1']
            output = self._run_snmp_command(cmd)
            
            if not output:
                return interfaces
            
            for line in output.splitlines():
                line = line.strip()
                if 'IpAddress:' in line:
                    try:
                        ip_addr = line.split(':')[-1].strip()
                        
                        # Get netmask for this IP using numeric OID
                        mask_cmd = ['snmpget', '-v2c', '-c', community, '-On', ip, f'1.3.6.1.2.1.4.20.1.3.{ip_addr}']
                        mask_output = self._run_snmp_command(mask_cmd)
                        
                        if mask_output and 'IpAddress:' in mask_output:
                            netmask = mask_output.split(':')[-1].strip()
                            interfaces.append({
                                'ip': ip_addr,
                                'netmask': netmask,
                                'name': f'if_{len(interfaces)}'
                            })
                    except Exception as e:
                        logger.debug(f"Failed to parse interface line: {line}, error: {e}")
                        continue
            
            return interfaces
            
        except Exception as e:
            logger.error(f"Failed to get interfaces from {ip}: {e}")
            return interfaces
    
    def test_connectivity(self, ip: str, community: str) -> bool:
        """Test if SNMP is working on the target."""
        try:
            cmd = ['snmpget', '-v2c', '-c', community, '-On', ip, '1.3.6.1.2.1.1.1.0']
            output = self._run_snmp_command(cmd)
            return output is not None
        except:
            return False
