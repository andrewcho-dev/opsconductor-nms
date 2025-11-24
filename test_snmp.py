#!/usr/bin/env python3
"""Test SNMP connectivity to 10.120.0.1"""
import asyncio
from pysnmp.hlapi.v1arch.asyncio import (
    get_cmd, SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity
)

async def test_snmp():
    target_ip = "10.120.0.1"
    community = "public"
    
    print(f"Testing SNMP connectivity to {target_ip} with community '{community}'...")
    
    try:
        snmp_dispatcher = SnmpDispatcher()
        community_data = CommunityData(community, mpModel=1)
        transport = await UdpTransportTarget.create((target_ip, 161), timeout=3.0, retries=2)
        
        print("Querying sysDescr (1.3.6.1.2.1.1.1.0)...")
        
        error_indication, error_status, error_index, var_binds = await get_cmd(
            snmp_dispatcher,
            community_data,
            transport,
            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0'))
        )
        
        if error_indication:
            print(f"ERROR - SNMP error indication: {error_indication}")
        elif error_status:
            print(f"ERROR - SNMP status error: {error_status.prettyPrint()}")
        else:
            print(f"SUCCESS - Device responded!")
            for var_bind in var_binds:
                print(f"  {var_bind[0]} = {var_bind[1]}")
        
        snmp_dispatcher.transport_dispatcher.close_dispatcher()
        
    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_snmp())
