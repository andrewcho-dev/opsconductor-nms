import asyncio
from app.database import async_session_factory, init_db, engine
from sqlalchemy import text


async def migrate():
    print("[MIGRATION] Adding mib_ids column to ip_inventory table")
    
    async with engine.begin() as conn:
        check_column = await conn.execute(
            text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='ip_inventory' AND column_name='mib_ids'
            """)
        )
        column_exists = check_column.fetchone() is not None
        
        if column_exists:
            print("[MIGRATION] Column mib_ids already exists, skipping")
            return
        
        print("[MIGRATION] Adding mib_ids column...")
        await conn.execute(
            text("ALTER TABLE ip_inventory ADD COLUMN mib_ids INTEGER[]")
        )
        
        print("[MIGRATION] Migrating existing mib_id values to mib_ids array...")
        await conn.execute(
            text("""
                UPDATE ip_inventory 
                SET mib_ids = ARRAY[mib_id]::INTEGER[] 
                WHERE mib_id IS NOT NULL AND (mib_ids IS NULL OR array_length(mib_ids, 1) IS NULL)
            """)
        )
        
        print("[MIGRATION] Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
