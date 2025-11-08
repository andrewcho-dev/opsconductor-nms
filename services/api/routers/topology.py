from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json
import httpx

router = APIRouter(prefix="/topology", tags=["topology"])

SFLOW_RT_URL = "http://localhost:8008"

class Device(BaseModel):
    name: str
    mgmt_ip: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    os_version: Optional[str]
    role: Optional[str]
    site: Optional[str]
    last_seen: Optional[datetime]

class Edge(BaseModel):
    edge_id: int
    a_dev: str
    a_if: str
    b_dev: str
    b_if: str
    method: str
    confidence: float
    first_seen: datetime
    last_seen: datetime
    evidence: dict

class PathHop(BaseModel):
    device: str
    interface: str
    method: str
    confidence: float

class PathResponse(BaseModel):
    path: List[PathHop]
    total_hops: int

class ImpactResponse(BaseModel):
    affected_devices: List[str]
    affected_count: int

@router.get("/nodes", response_model=List[Device])
async def get_nodes(
    site: Optional[str] = None,
    role: Optional[str] = None
):
    from main import db_pool
    
    query = "SELECT name, mgmt_ip, vendor, model, os_version, role, site, last_seen FROM devices WHERE 1=1"
    params = []
    
    if site:
        query += " AND site = $" + str(len(params) + 1)
        params.append(site)
    
    if role:
        query += " AND role = $" + str(len(params) + 1)
        params.append(role)
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [
            Device(
                name=row['name'],
                mgmt_ip=str(row['mgmt_ip']) if row['mgmt_ip'] else None,
                vendor=row['vendor'],
                model=row['model'],
                os_version=row['os_version'],
                role=row['role'],
                site=row['site'],
                last_seen=row['last_seen']
            )
            for row in rows
        ]

@router.get("/edges", response_model=List[Edge])
async def get_edges(
    site: Optional[str] = None,
    role: Optional[str] = None,
    min_conf: float = Query(0.0, ge=0.0, le=1.0)
):
    from main import db_pool
    
    query = """
        SELECT e.edge_id, e.a_dev, e.a_if, e.b_dev, e.b_if, e.method, 
               e.confidence, e.first_seen, e.last_seen, e.evidence
        FROM vw_links_canonical e
        WHERE e.confidence >= $1
    """
    params = [min_conf]
    
    if site or role:
        query += " AND (e.a_dev IN (SELECT name FROM devices WHERE 1=1"
        if site:
            query += " AND site = $" + str(len(params) + 1)
            params.append(site)
        if role:
            query += " AND role = $" + str(len(params) + 1)
            params.append(role)
        query += ") OR e.b_dev IN (SELECT name FROM devices WHERE 1=1"
        if site:
            query += " AND site = $" + str(len(params) - (1 if role else 0))
        if role:
            query += " AND role = $" + str(len(params))
        query += "))"
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [
            Edge(
                edge_id=row['edge_id'],
                a_dev=row['a_dev'],
                a_if=row['a_if'],
                b_dev=row['b_dev'],
                b_if=row['b_if'],
                method=row['method'],
                confidence=float(row['confidence']),
                first_seen=row['first_seen'],
                last_seen=row['last_seen'],
                evidence=json.loads(row['evidence']) if isinstance(row['evidence'], str) else row['evidence']
            )
            for row in rows
        ]

@router.get("/path", response_model=PathResponse)
async def get_path(
    src_dev: str,
    src_if: Optional[str] = None,
    dst_dev: Optional[str] = None,
    dst_if: Optional[str] = None,
    layer: str = Query("2", regex="^[23]$")
):
    from main import db_pool
    
    if not dst_dev:
        raise HTTPException(status_code=400, detail="dst_dev is required")
    
    async with db_pool.acquire() as conn:
        query = """
            WITH RECURSIVE path_search AS (
                SELECT 
                    a_dev as device,
                    a_if as interface,
                    b_dev as next_device,
                    b_if as next_interface,
                    method,
                    confidence,
                    ARRAY[a_dev] as visited,
                    1 as hop_count
                FROM vw_links_canonical
                WHERE a_dev = $1
                  AND ($2::text IS NULL OR a_if = $2)
                
                UNION ALL
                
                SELECT 
                    e.a_dev,
                    e.a_if,
                    e.b_dev,
                    e.b_if,
                    e.method,
                    e.confidence,
                    ps.visited || e.a_dev,
                    ps.hop_count + 1
                FROM path_search ps
                JOIN vw_links_canonical e ON ps.next_device = e.a_dev
                WHERE NOT (e.a_dev = ANY(ps.visited))
                  AND ps.hop_count < 20
            )
            SELECT device, interface, method, confidence
            FROM path_search
            WHERE next_device = $3
              AND ($4::text IS NULL OR next_interface = $4)
            ORDER BY hop_count
            LIMIT 1
        """
        
        rows = await conn.fetch(query, src_dev, src_if, dst_dev, dst_if)
        
        if not rows:
            return PathResponse(path=[], total_hops=0)
        
        path = [
            PathHop(
                device=row['device'],
                interface=row['interface'],
                method=row['method'],
                confidence=float(row['confidence'])
            )
            for row in rows
        ]
        
        return PathResponse(path=path, total_hops=len(path))

@router.get("/impact", response_model=ImpactResponse)
async def get_impact(
    node: str,
    port: Optional[str] = None,
    layer: str = Query("2", regex="^[23]$")
):
    from main import db_pool
    
    async with db_pool.acquire() as conn:
        query = """
            WITH RECURSIVE downstream (device, depth) AS (
                SELECT DISTINCT 
                    CASE 
                        WHEN a_dev = $1 THEN b_dev
                        ELSE a_dev
                    END as device,
                    1 as depth
                FROM vw_links_canonical
                WHERE (a_dev = $1 OR b_dev = $1)
                  AND ($2::text IS NULL OR a_if = $2 OR b_if = $2)
                
                UNION ALL
                
                SELECT DISTINCT 
                    CASE 
                        WHEN e.a_dev = d.device THEN e.b_dev
                        ELSE e.a_dev
                    END as device,
                    d.depth + 1
                FROM downstream d
                JOIN vw_links_canonical e ON (d.device = e.a_dev OR d.device = e.b_dev)
                WHERE CASE 
                        WHEN e.a_dev = d.device THEN e.b_dev
                        ELSE e.a_dev
                      END != $1
                  AND d.depth < 20
            )
            SELECT DISTINCT device FROM downstream
        """
        
        rows = await conn.fetch(query, node, port)
        devices = [row['device'] for row in rows]
        
        return ImpactResponse(
            affected_devices=devices,
            affected_count=len(devices)
        )

class Interface(BaseModel):
    device: str
    ifname: str
    admin_up: bool
    oper_up: bool
    speed_mbps: Optional[int]
    vlan: Optional[str]
    l3_addr: Optional[str]
    l2_mac: Optional[str]
    last_seen: Optional[datetime]

@router.get("/interface", response_model=Interface)
async def get_interface(
    device: str,
    ifname: str
):
    from main import db_pool
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT device, ifname, admin_up, oper_up, speed_mbps, vlan, l3_addr, l2_mac, last_seen
            FROM interfaces
            WHERE device = $1 AND ifname = $2
        """, device, ifname)
        
        if not row:
            raise HTTPException(status_code=404, detail="Interface not found")
        
        return Interface(
            device=row['device'],
            ifname=row['ifname'],
            admin_up=row['admin_up'],
            oper_up=row['oper_up'],
            speed_mbps=row['speed_mbps'],
            vlan=row['vlan'],
            l3_addr=str(row['l3_addr']) if row['l3_addr'] else None,
            l2_mac=str(row['l2_mac']) if row['l2_mac'] else None,
            last_seen=row['last_seen']
        )

class FlowData(BaseModel):
    agent: str
    interface: str
    bytes_per_sec: float
    packets_per_sec: float

@router.get("/flows", response_model=List[FlowData])
async def get_flows():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SFLOW_RT_URL}/dump/ALL/ifinoctets/json")
            if response.status_code == 200:
                data = response.json()
                flows = []
                for agent_data in data:
                    agent = agent_data.get('agent', '')
                    for iface, stats in agent_data.get('metricValue', {}).items():
                        flows.append(FlowData(
                            agent=agent,
                            interface=iface,
                            bytes_per_sec=stats.get('metricValue', 0),
                            packets_per_sec=0
                        ))
                return flows
    except Exception as e:
        return []
    return []

@router.get("/edges/enriched", response_model=List[Dict[str, Any]])
async def get_enriched_edges(
    site: Optional[str] = None,
    role: Optional[str] = None,
    min_conf: float = Query(0.0, ge=0.0, le=1.0)
):
    from main import db_pool
    
    edges_data = await get_edges(site, role, min_conf)
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SFLOW_RT_URL}/metric/ALL/ifinoctets/json")
            flows = {}
            if response.status_code == 200:
                data = response.json()
                for item in data:
                    agent = item.get('agent', '')
                    iface = item.get('dataSource', '').split('.')[-1] if item.get('dataSource') else ''
                    value = item.get('metricValue', 0)
                    if agent and iface:
                        flows[f"{agent}:{iface}"] = value
    except Exception as e:
        flows = {}
    
    enriched = []
    for edge in edges_data:
        edge_dict = edge.dict()
        src_key = f"{edge.a_dev}:{edge.a_if}"
        dst_key = f"{edge.b_dev}:{edge.b_if}"
        edge_dict['utilization_bps'] = flows.get(src_key, 0)
        edge_dict['flow_detected'] = src_key in flows or dst_key in flows
        enriched.append(edge_dict)
    
    return enriched
