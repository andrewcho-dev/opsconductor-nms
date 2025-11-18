import asyncio
from app.database import async_session_factory, init_db
from app.models import Mib
from sqlalchemy import select


COMMON_MIBS = [
    {
        "name": "SNMPv2-MIB",
        "vendor": "IETF",
        "device_types": ["router", "switch", "network_device", "linux_host", "windows_host"],
        "version": "RFC 3418",
        "file_path": "/usr/share/snmp/mibs/ietf/SNMPv2-MIB",
        "description": "Standard SNMP MIB-2 for all devices (sysDescr, sysName, sysLocation, etc.)"
    },
    {
        "name": "IF-MIB",
        "vendor": "IETF",
        "device_types": ["router", "switch", "network_device"],
        "version": "RFC 2863",
        "file_path": "/usr/share/snmp/mibs/ietf/IF-MIB",
        "description": "Interface MIB for network interface statistics"
    },
    {
        "name": "IP-MIB",
        "vendor": "IETF",
        "device_types": ["router", "switch", "network_device", "linux_host"],
        "version": "RFC 4293",
        "file_path": "/usr/share/snmp/mibs/ietf/IP-MIB",
        "description": "IP protocol statistics and configuration"
    },
    {
        "name": "CISCO-ENHANCED-IMAGE-MIB",
        "vendor": "Cisco",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-ENHANCED-IMAGE-MIB",
        "description": "Cisco device image and version information"
    },
    {
        "name": "CISCO-PROCESS-MIB",
        "vendor": "Cisco",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-PROCESS-MIB",
        "description": "Cisco CPU and process utilization"
    },
    {
        "name": "CISCO-MEMORY-POOL-MIB",
        "vendor": "Cisco",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-MEMORY-POOL-MIB",
        "description": "Cisco memory pool statistics"
    },
    {
        "name": "CISCO-VLAN-MEMBERSHIP-MIB",
        "vendor": "Cisco",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-VLAN-MEMBERSHIP-MIB",
        "description": "Cisco VLAN configuration and membership"
    },
    {
        "name": "HP-ICF-OID",
        "vendor": "HP",
        "device_types": ["switch", "network_device", "printer"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/hp/HP-ICF-OID",
        "description": "HP device identification and OIDs"
    },
    {
        "name": "HP-SWITCH-MIB",
        "vendor": "HP",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/hp/HP-SWITCH-MIB",
        "description": "HP switch configuration and statistics"
    },
    {
        "name": "PRINTER-MIB",
        "vendor": "IETF",
        "device_types": ["printer"],
        "version": "RFC 3805",
        "file_path": "/usr/share/snmp/mibs/ietf/PRINTER-MIB",
        "description": "Standard printer status and supplies"
    },
    {
        "name": "HOST-RESOURCES-MIB",
        "vendor": "IETF",
        "device_types": ["linux_host", "windows_host"],
        "version": "RFC 2790",
        "file_path": "/usr/share/snmp/mibs/ietf/HOST-RESOURCES-MIB",
        "description": "Host system resources (CPU, memory, disk, processes)"
    },
    {
        "name": "UCD-SNMP-MIB",
        "vendor": "Net-SNMP",
        "device_types": ["linux_host"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/net-snmp/UCD-SNMP-MIB",
        "description": "Net-SNMP Linux system statistics"
    },
    {
        "name": "JUNIPER-MIB",
        "vendor": "Juniper",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/juniper/JUNIPER-MIB",
        "description": "Juniper Networks device information"
    },
    {
        "name": "ARISTA-ENTITY-SENSOR-MIB",
        "vendor": "Arista",
        "device_types": ["switch", "router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/arista/ARISTA-ENTITY-SENSOR-MIB",
        "description": "Arista switch sensor monitoring"
    },
    {
        "name": "DELL-VENDOR-MIB",
        "vendor": "Dell",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dell/DELL-VENDOR-MIB",
        "description": "Dell networking device information"
    },
    {
        "name": "TP-LINK-SWITCH-MIB",
        "vendor": "TP-Link",
        "device_types": ["switch", "router", "network_device", "access_point"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/tplink/TP-LINK-SWITCH-MIB",
        "description": "TP-Link switch and router configuration"
    },
    {
        "name": "AXIS-VIDEO-MIB",
        "vendor": "Axis",
        "device_types": ["ip_camera"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/axis/AXIS-VIDEO-MIB",
        "description": "Axis IP camera video stream information"
    },
    {
        "name": "AXIS-ROOT-MIB",
        "vendor": "Axis",
        "device_types": ["ip_camera", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/axis/AXIS-ROOT-MIB",
        "description": "Axis device identification and status"
    },
    {
        "name": "ENTITY-MIB",
        "vendor": "IETF",
        "device_types": ["router", "switch", "network_device"],
        "version": "RFC 6933",
        "file_path": "/usr/share/snmp/mibs/ietf/ENTITY-MIB",
        "description": "Physical entity hierarchy and inventory"
    },
    {
        "name": "BRIDGE-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "network_device"],
        "version": "RFC 4188",
        "file_path": "/usr/share/snmp/mibs/ietf/BRIDGE-MIB",
        "description": "Bridge/switch forwarding database and spanning tree"
    },
    {
        "name": "Q-BRIDGE-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "network_device"],
        "version": "RFC 4363",
        "oid_prefix": "1.3.6.1.2.1.17.7",
        "file_path": "/usr/share/snmp/mibs/ietf/Q-BRIDGE-MIB",
        "description": "VLAN management and 802.1Q bridge configuration"
    },
    {
        "name": "POWER-ETHERNET-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "network_device"],
        "version": "RFC 3621",
        "oid_prefix": "1.3.6.1.2.1.105",
        "file_path": "/usr/share/snmp/mibs/ietf/POWER-ETHERNET-MIB",
        "description": "Power over Ethernet port status and power consumption"
    },
    {
        "name": "LLDP-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "router", "network_device"],
        "version": "IEEE 802.1AB",
        "oid_prefix": "1.0.8802.1.1.2",
        "file_path": "/usr/share/snmp/mibs/ietf/LLDP-MIB",
        "description": "Link Layer Discovery Protocol for neighbor discovery"
    },
    {
        "name": "LLDP-EXT-DOT1-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "network_device"],
        "version": "IEEE 802.1AB",
        "oid_prefix": "1.0.8802.1.1.2.1.5.32962",
        "file_path": "/usr/share/snmp/mibs/ietf/LLDP-EXT-DOT1-MIB",
        "description": "LLDP extensions for VLAN and protocol information"
    },
    {
        "name": "LLDP-EXT-DOT3-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "network_device"],
        "version": "IEEE 802.1AB",
        "oid_prefix": "1.0.8802.1.1.2.1.5.4623",
        "file_path": "/usr/share/snmp/mibs/ietf/LLDP-EXT-DOT3-MIB",
        "description": "LLDP extensions for POE and link aggregation"
    },
    {
        "name": "EtherLike-MIB",
        "vendor": "IETF",
        "device_types": ["switch", "router", "network_device"],
        "version": "RFC 3635",
        "oid_prefix": "1.3.6.1.2.1.10.7",
        "file_path": "/usr/share/snmp/mibs/ietf/EtherLike-MIB",
        "description": "Ethernet interface statistics and error counters"
    },
    {
        "name": "OSPF-MIB",
        "vendor": "IETF",
        "device_types": ["router", "network_device"],
        "version": "RFC 4750",
        "oid_prefix": "1.3.6.1.2.1.14",
        "file_path": "/usr/share/snmp/mibs/ietf/OSPF-MIB",
        "description": "OSPF routing protocol configuration and neighbors"
    },
    {
        "name": "BGP4-MIB",
        "vendor": "IETF",
        "device_types": ["router", "network_device"],
        "version": "RFC 4273",
        "oid_prefix": "1.3.6.1.2.1.15",
        "file_path": "/usr/share/snmp/mibs/ietf/BGP4-MIB",
        "description": "BGP routing protocol peer information"
    },
    {
        "name": "CIENA-CES-MIB",
        "vendor": "Ciena",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-CES-MIB",
        "oid_prefix": "1.3.6.1.4.1.6141",
        "description": "Ciena Carrier Ethernet Services MIB"
    },
    {
        "name": "CIENA-GLOBAL-MIB",
        "vendor": "Ciena",
        "device_types": ["router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-GLOBAL-MIB",
        "oid_prefix": "1.3.6.1.4.1.6141",
        "description": "Ciena global device identification and status"
    },
    {
        "name": "DLINK-EQUIPMENT-MIB",
        "vendor": "D-Link",
        "device_types": ["switch", "router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dlink/DLINK-EQUIPMENT-MIB",
        "oid_prefix": "1.3.6.1.4.1.171",
        "description": "D-Link switch and router equipment monitoring"
    },
    {
        "name": "DLINK-DGS-SWITCH-MIB",
        "vendor": "D-Link",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dlink/DLINK-DGS-SWITCH-MIB",
        "oid_prefix": "1.3.6.1.4.1.171",
        "description": "D-Link DGS series switch configuration"
    },
    {
        "name": "CANON-PRINTER-MIB",
        "vendor": "Canon",
        "device_types": ["printer"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/canon/CANON-PRINTER-MIB",
        "description": "Canon printer status and supplies monitoring"
    },
    {
        "name": "YEALINK-MIB",
        "vendor": "Yealink",
        "device_types": ["voip_phone", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/yealink/YEALINK-MIB",
        "description": "Yealink VoIP phone status and configuration"
    },
    {
        "name": "HP-LASERJET-COMMON-MIB",
        "vendor": "HP",
        "device_types": ["printer"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/hp/HP-LASERJET-COMMON-MIB",
        "description": "HP LaserJet printer status and supplies"
    },
    {
        "name": "CRADLEPOINT-MIB",
        "vendor": "Cradlepoint",
        "device_types": ["router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cradlepoint/CRADLEPOINT-MIB",
        "description": "Cradlepoint router status and configuration"
    },
    {
        "name": "CISCO-FIREWALL-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-FIREWALL-MIB",
        "oid_prefix": "1.3.6.1.4.1.9",
        "description": "Cisco ASA firewall connections and statistics"
    },
    {
        "name": "CISCO-REMOTE-ACCESS-MONITOR-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-REMOTE-ACCESS-MONITOR-MIB",
        "oid_prefix": "1.3.6.1.4.1.9",
        "description": "Cisco ASA VPN and remote access monitoring"
    },
    {
        "name": "RAZBERI-MONITOR-MIB",
        "vendor": "Razberi",
        "device_types": ["nvr", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/razberi/RAZBERI-MONITOR-MIB",
        "description": "Razberi NVR health and surveillance monitoring"
    },
    {
        "name": "TPLINK-ROUTER-MIB",
        "vendor": "TP-Link",
        "device_types": ["router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/tplink/TPLINK-ROUTER-MIB",
        "oid_prefix": "1.3.6.1.4.1.11863.2",
        "description": "TP-Link Omada router/gateway configuration and status"
    },
    {
        "name": "TPLINK-WIRELESS-MIB",
        "vendor": "TP-Link",
        "device_types": ["access_point", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/tplink/TPLINK-WIRELESS-MIB",
        "oid_prefix": "1.3.6.1.4.1.11863.3",
        "description": "TP-Link Omada wireless access point configuration and statistics"
    },
    {
        "name": "IDRAC-MIB",
        "vendor": "Dell",
        "device_types": ["server", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dell/IDRAC-MIB",
        "oid_prefix": "1.3.6.1.4.1.674.10892.5",
        "description": "Dell iDRAC integrated remote access controller monitoring"
    },
    {
        "name": "DELL-RAC-MIB",
        "vendor": "Dell",
        "device_types": ["server", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dell/DELL-RAC-MIB",
        "oid_prefix": "1.3.6.1.4.1.674.10892",
        "description": "Dell Remote Access Controller hardware health and status"
    },
    {
        "name": "DELL10892-MIB",
        "vendor": "Dell",
        "device_types": ["server", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/dell/DELL10892-MIB",
        "oid_prefix": "1.3.6.1.4.1.674.10892",
        "description": "Dell server hardware status, sensors, and power supply"
    },
    {
        "name": "SIKLU-MIB",
        "vendor": "Siklu",
        "device_types": ["radio", "wireless_bridge", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/siklu/SIKLU-MIB",
        "oid_prefix": "1.3.6.1.4.1.31926",
        "description": "Siklu millimeter wave radio link status and performance"
    },
    {
        "name": "SIKLU-DEVICE-MIB",
        "vendor": "Siklu",
        "device_types": ["radio", "wireless_bridge", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/siklu/SIKLU-DEVICE-MIB",
        "oid_prefix": "1.3.6.1.4.1.31926",
        "description": "Siklu device information and configuration"
    },
    {
        "name": "UBNT-MIB",
        "vendor": "Ubiquiti",
        "device_types": ["radio", "wireless_bridge", "access_point", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ubiquiti/UBNT-MIB",
        "oid_prefix": "1.3.6.1.4.1.41112",
        "description": "Ubiquiti airMAX radio and UniFi device monitoring"
    },
    {
        "name": "UBNT-UniFi-MIB",
        "vendor": "Ubiquiti",
        "device_types": ["access_point", "switch", "router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ubiquiti/UBNT-UniFi-MIB",
        "oid_prefix": "1.3.6.1.4.1.41112.1.6",
        "description": "Ubiquiti UniFi access point and controller statistics"
    },
    {
        "name": "UBNT-AirMAX-MIB",
        "vendor": "Ubiquiti",
        "device_types": ["radio", "wireless_bridge", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ubiquiti/UBNT-AirMAX-MIB",
        "oid_prefix": "1.3.6.1.4.1.41112.1.4",
        "description": "Ubiquiti airMAX wireless link quality and throughput"
    },
    {
        "name": "CISCO-SYSLOG-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-SYSLOG-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.9.41",
        "description": "Cisco ASA and device syslog configuration and messages"
    },
    {
        "name": "CISCO-ENTITY-FRU-CONTROL-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-ENTITY-FRU-CONTROL-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.9.117",
        "description": "Cisco ASA field replaceable unit power and cooling"
    },
    {
        "name": "CISCO-ENTITY-VENDORTYPE-OID-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-ENTITY-VENDORTYPE-OID-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.12.3",
        "description": "Cisco ASA and device hardware identification"
    },
    {
        "name": "CISCO-IPSEC-FLOW-MONITOR-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "router", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-IPSEC-FLOW-MONITOR-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.9.171",
        "description": "Cisco ASA IPSec VPN tunnel monitoring and statistics"
    },
    {
        "name": "CISCO-UNIFIED-FIREWALL-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-UNIFIED-FIREWALL-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.9.491",
        "description": "Cisco ASA unified threat management statistics"
    },
    {
        "name": "CISCO-ENTITY-SENSOR-MIB",
        "vendor": "Cisco",
        "device_types": ["firewall", "router", "switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/cisco/CISCO-ENTITY-SENSOR-MIB",
        "oid_prefix": "1.3.6.1.4.1.9.9.91",
        "description": "Cisco ASA temperature and hardware sensor monitoring"
    },
    {
        "name": "VERACITY-MIB",
        "vendor": "Veracity",
        "device_types": ["ethernet_extender", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/veracity/VERACITY-MIB",
        "oid_prefix": "1.3.6.1.4.1.32185",
        "description": "Veracity ethernet over coax extender status and configuration"
    },
    {
        "name": "VERACITY-DEVICE-MIB",
        "vendor": "Veracity",
        "device_types": ["ethernet_extender", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/veracity/VERACITY-DEVICE-MIB",
        "oid_prefix": "1.3.6.1.4.1.32185",
        "description": "Veracity device information and link quality monitoring"
    },
    {
        "name": "MILESTONE-MIB",
        "vendor": "Milestone",
        "device_types": ["vms", "nvr", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/milestone/MILESTONE-MIB",
        "oid_prefix": "1.3.6.1.4.1.35901",
        "description": "Milestone XProtect VMS server status and recording statistics"
    },
    {
        "name": "MILESTONE-XPROTECT-MIB",
        "vendor": "Milestone",
        "device_types": ["vms", "nvr", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/milestone/MILESTONE-XPROTECT-MIB",
        "oid_prefix": "1.3.6.1.4.1.35901",
        "description": "Milestone XProtect camera status, recording server health, and storage monitoring"
    },
    {
        "name": "CIENA-WS-MIB",
        "vendor": "Ciena",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-WS-MIB",
        "oid_prefix": "1.3.6.1.4.1.1271",
        "description": "Ciena Waveserver and 3000 series switch platform monitoring"
    },
    {
        "name": "CIENA-WS-TYPEDEFS-MIB",
        "vendor": "Ciena",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-WS-TYPEDEFS-MIB",
        "oid_prefix": "1.3.6.1.4.1.1271",
        "description": "Ciena switch type definitions and common objects"
    },
    {
        "name": "CIENA-CES-CHASSIS-MIB",
        "vendor": "Ciena",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-CES-CHASSIS-MIB",
        "oid_prefix": "1.3.6.1.4.1.6141",
        "description": "Ciena switch chassis hardware inventory and status"
    },
    {
        "name": "CIENA-CES-PORT-MIB",
        "vendor": "Ciena",
        "device_types": ["switch", "network_device"],
        "version": "1.0",
        "file_path": "/usr/share/snmp/mibs/ciena/CIENA-CES-PORT-MIB",
        "oid_prefix": "1.3.6.1.4.1.6141",
        "description": "Ciena switch port configuration and statistics"
    }
]


async def populate_mibs():
    await init_db()
    
    async with async_session_factory() as session:
        result = await session.execute(select(Mib))
        existing_mibs = {mib.name for mib in result.scalars().all()}
        
        added = 0
        skipped = 0
        
        for mib_data in COMMON_MIBS:
            if mib_data["name"] in existing_mibs:
                print(f"[MIB] Skipping {mib_data['name']} (already exists)")
                skipped += 1
                continue
            
            mib = Mib(**mib_data)
            session.add(mib)
            added += 1
            print(f"[MIB] Added {mib_data['name']} ({mib_data['vendor']})")
        
        await session.commit()
        print(f"\n[MIB] Population complete: {added} added, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(populate_mibs())
