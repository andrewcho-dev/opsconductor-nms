from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
import os
import asyncpg
from netbox_client import NetBoxClient, NetBoxDevice, NetBoxCable

router = APIRouter(prefix="/netbox", tags=["netbox"])

def get_netbox_client() -> NetBoxClient:
    netbox_url = os.getenv("NETBOX_URL")
    netbox_token = os.getenv("NETBOX_API_TOKEN")
    
    if not netbox_url or not netbox_token:
        raise HTTPException(
            status_code=503,
            detail="NetBox integration not configured. Set NETBOX_URL and NETBOX_API_TOKEN environment variables."
        )
    
    return NetBoxClient(netbox_url, netbox_token)

@router.post("/sync/devices")
async def sync_devices_to_netbox(
    site: Optional[str] = Query(None, description="Filter by site"),
    client: NetBoxClient = Depends(get_netbox_client)
):
    from main import db_pool
    
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        async with db_pool.acquire() as conn:
            query = "SELECT name, vendor, model, site, role FROM devices WHERE 1=1"
            params = []
            
            if site:
                query += " AND site = $1"
                params.append(site)
            
            devices = await conn.fetch(query, *params)
        
        results = {"success": [], "failed": []}
        
        for device in devices:
            nb_device = NetBoxDevice(
                name=device['name'],
                device_type=device['model'] or "Unknown",
                site=device['site'] or "default",
                manufacturer=device['vendor'],
                model=device['model'],
                role=device['role']
            )
            
            result = await client.upsert_device(nb_device)
            
            if result:
                results['success'].append(device['name'])
            else:
                results['failed'].append(device['name'])
        
        return {
            "status": "completed",
            "synced": len(results['success']),
            "failed": len(results['failed']),
            "details": results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing devices: {str(e)}")

@router.post("/sync/cables")
async def sync_cables_to_netbox(
    min_confidence: float = Query(0.8, ge=0.0, le=1.0),
    client: NetBoxClient = Depends(get_netbox_client)
):
    from main import db_pool
    
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        async with db_pool.acquire() as conn:
            query = """
                SELECT DISTINCT
                    a_dev, a_if, b_dev, b_if, method, confidence
                FROM vw_links_canonical
                WHERE confidence >= $1
                AND method = 'lldp'
                ORDER BY a_dev, a_if
            """
            edges = await conn.fetch(query, min_confidence)
        
        results = {"success": [], "failed": []}
        
        for edge in edges:
            nb_cable = NetBoxCable(
                device_a=edge['a_dev'],
                interface_a=edge['a_if'],
                device_b=edge['b_dev'],
                interface_b=edge['b_if'],
                label=f"{edge['method']} ({edge['confidence']:.0%})"
            )
            
            result = await client.upsert_cable(nb_cable)
            
            if result:
                results['success'].append(f"{edge['a_dev']}:{edge['a_if']} <-> {edge['b_dev']}:{edge['b_if']}")
            else:
                results['failed'].append(f"{edge['a_dev']}:{edge['a_if']} <-> {edge['b_dev']}:{edge['b_if']}")
        
        return {
            "status": "completed",
            "synced": len(results['success']),
            "failed": len(results['failed']),
            "details": results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing cables: {str(e)}")

@router.post("/sync/all")
async def sync_all_to_netbox(
    site: Optional[str] = Query(None),
    min_confidence: float = Query(0.8, ge=0.0, le=1.0),
    client: NetBoxClient = Depends(get_netbox_client)
):
    devices_result = await sync_devices_to_netbox(site, client)
    cables_result = await sync_cables_to_netbox(min_confidence, client)
    
    return {
        "status": "completed",
        "devices": devices_result,
        "cables": cables_result
    }
