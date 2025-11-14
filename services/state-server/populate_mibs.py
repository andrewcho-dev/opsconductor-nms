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
