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
