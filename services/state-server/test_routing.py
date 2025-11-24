#!/usr/bin/env python3
"""Test routing table fetch from 10.120.0.1"""
import asyncio
import sys
sys.path.insert(0, '/home/opsconductor/opsconductor-nms/services/state-server')
from snmp_routing import get_routing_entries_async

async def test_routing():
    target_ip = "10.120.0.1"
    community = "public"
    version = "2c"
    
    print(f"Fetching routing table from {target_ip}...")
    print("=" * 60)
    
    try:
        routes = await get_routing_entries_async(target_ip, community, version)
        
        print(f"\nFound {len(routes)} routes:")
        print("=" * 60)
        
        for i, route in enumerate(routes, 1):
            print(f"\nRoute {i}:")
            print(f"  Destination: {route.destination_ip}/{route.netmask}")
            print(f"  Next Hop: {route.next_hop or 'directly connected'}")
            print(f"  Protocol: {route.protocol or 'unknown'}")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_routing())
