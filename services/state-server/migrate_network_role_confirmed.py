#!/usr/bin/env python3
import asyncio
import asyncpg
import os

async def migrate():
    db_url = os.getenv("DB_URL", "postgresql://topo:topo@postgres:5432/topology")
    
    parts = db_url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db = parts[1].split("/")
    host_port = host_db[0].split(":")
    
    user = user_pass[0]
    password = user_pass[1]
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 5432
    database = host_db[1]
    
    conn = await asyncpg.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database
    )
    
    try:
        column_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = 'ip_inventory' 
                AND column_name = 'network_role_confirmed'
            );
        """)
        
        if not column_exists:
            print("Adding network_role_confirmed column...")
            await conn.execute("""
                ALTER TABLE ip_inventory 
                ADD COLUMN network_role_confirmed BOOLEAN DEFAULT FALSE;
            """)
            print("Column added successfully!")
        else:
            print("Column network_role_confirmed already exists, skipping migration.")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
