from fastapi import APIRouter, Query
from typing import Optional, List
from sflow_client import sflow_client

router = APIRouter(prefix="/sflow", tags=["sflow"])

@router.get("/utilization/{interface}")
async def get_interface_utilization(interface: str):
    data = await sflow_client.get_interface_utilization(interface)
    return data or {"error": "No data available"}

@router.get("/flows")
async def get_flows(
    limit: int = Query(100, ge=1, le=1000),
    src_ip: Optional[str] = None,
    dst_ip: Optional[str] = None
):
    if src_ip or dst_ip:
        flows = await sflow_client.get_flow_between_hosts(src_ip, dst_ip)
    else:
        flows = await sflow_client.get_top_flows(limit)
    return {"flows": flows}

@router.get("/counters")
async def get_counters():
    data = await sflow_client.get_interface_counters()
    return data
