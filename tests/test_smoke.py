import pytest
import asyncio
import asyncpg
import json
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_DSN = os.getenv('TEST_PG_DSN', 'postgresql://oc:oc@localhost/opsconductor_test')

@pytest.fixture
async def db_pool():
    pool = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=5)
    
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS edges CASCADE")
        await conn.execute("DROP TABLE IF EXISTS interfaces CASCADE")
        await conn.execute("DROP TABLE IF EXISTS devices CASCADE")
        await conn.execute("DROP TABLE IF EXISTS facts_lldp CASCADE")
        await conn.execute("DROP TABLE IF EXISTS facts_cdp CASCADE")
        await conn.execute("DROP TABLE IF EXISTS facts_mac CASCADE")
        await conn.execute("DROP TABLE IF EXISTS facts_arp CASCADE")
        await conn.execute("DROP TABLE IF EXISTS hostname_mappings CASCADE")
        
        migration_file = Path(__file__).parent.parent / "services/api/migrations/0001_init.sql"
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
            await conn.execute(migration_sql)
    
    yield pool
    
    await pool.close()

@pytest.mark.asyncio
async def test_device_insertion(db_pool):
    with open(FIXTURES_DIR / "sample_devices.json") as f:
        devices = json.load(f)
    
    async with db_pool.acquire() as conn:
        for device in devices:
            await conn.execute("""
                INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, device['name'], device['mgmt_ip'], device['vendor'], 
                device['model'], device['os_version'], device['role'], device['site'])
        
        count = await conn.fetchval("SELECT COUNT(*) FROM devices")
        assert count == len(devices)

@pytest.mark.asyncio
async def test_edge_creation(db_pool):
    with open(FIXTURES_DIR / "sample_devices.json") as f:
        devices = json.load(f)
    
    with open(FIXTURES_DIR / "sample_edges.json") as f:
        edges = json.load(f)
    
    async with db_pool.acquire() as conn:
        for device in devices:
            await conn.execute("""
                INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (name) DO NOTHING
            """, device['name'], device['mgmt_ip'], device['vendor'], 
                device['model'], device['os_version'], device['role'], device['site'])
        
        for edge in edges:
            await conn.execute("""
                INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, edge['a_dev'], edge['a_if'], edge['b_dev'], edge['b_if'],
                edge['method'], edge['confidence'], json.dumps(edge['evidence']))
        
        edge_count = await conn.fetchval("SELECT COUNT(*) FROM edges")
        assert edge_count == len(edges)

@pytest.mark.asyncio
async def test_canonical_links_view(db_pool):
    with open(FIXTURES_DIR / "sample_devices.json") as f:
        devices = json.load(f)
    
    with open(FIXTURES_DIR / "sample_edges.json") as f:
        edges = json.load(f)
    
    async with db_pool.acquire() as conn:
        for device in devices:
            await conn.execute("""
                INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (name) DO NOTHING
            """, device['name'], device['mgmt_ip'], device['vendor'], 
                device['model'], device['os_version'], device['role'], device['site'])
        
        for edge in edges:
            await conn.execute("""
                INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, edge['a_dev'], edge['a_if'], edge['b_dev'], edge['b_if'],
                edge['method'], edge['confidence'], json.dumps(edge['evidence']))
        
        canonical_links = await conn.fetch("SELECT * FROM vw_links_canonical")
        assert len(canonical_links) >= 1
        assert canonical_links[0]['method'] == 'lldp'

@pytest.mark.asyncio
async def test_path_query(db_pool):
    with open(FIXTURES_DIR / "sample_devices.json") as f:
        devices = json.load(f)
    
    with open(FIXTURES_DIR / "sample_edges.json") as f:
        edges = json.load(f)
    
    async with db_pool.acquire() as conn:
        for device in devices:
            await conn.execute("""
                INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (name) DO NOTHING
            """, device['name'], device['mgmt_ip'], device['vendor'], 
                device['model'], device['os_version'], device['role'], device['site'])
        
        for edge in edges:
            await conn.execute("""
                INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, edge['a_dev'], edge['a_if'], edge['b_dev'], edge['b_if'],
                edge['method'], edge['confidence'], json.dumps(edge['evidence']))
        
        path_query = """
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
            WHERE next_device = $2
            ORDER BY hop_count
            LIMIT 1
        """
        
        path = await conn.fetch(path_query, 'test-router-1', 'test-switch-1')
        assert len(path) >= 1
        assert path[0]['device'] == 'test-router-1'
