#!/usr/bin/env python3
"""
Migration script to add nmap-related fields to ip_inventory table
"""
import asyncio
import sys
from sqlalchemy import text
from app.database import async_engine


async def migrate():
    print("[MIGRATE] Adding nmap fields to ip_inventory table...", flush=True)
    
    async with async_engine.begin() as conn:
        await conn.execute(text("""
            ALTER TABLE ip_inventory 
            ADD COLUMN IF NOT EXISTS all_hostnames TEXT[],
            ADD COLUMN IF NOT EXISTS os_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS os_accuracy VARCHAR(10),
            ADD COLUMN IF NOT EXISTS os_detection JSONB,
            ADD COLUMN IF NOT EXISTS uptime_seconds VARCHAR(50),
            ADD COLUMN IF NOT EXISTS host_scripts JSONB,
            ADD COLUMN IF NOT EXISTS nmap_scan_time TIMESTAMP WITH TIME ZONE
        """))
        
        print("[MIGRATE] Successfully added nmap fields", flush=True)
    
    await async_engine.dispose()
    print("[MIGRATE] Migration complete!", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(migrate())
    except Exception as e:
        print(f"[MIGRATE] Error: {e}", flush=True)
        sys.exit(1)
