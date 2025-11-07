import os
import sys
import psycopg2
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_db(dsn, max_retries=30, delay=2):
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(dsn)
            conn.close()
            logger.info("Database is ready")
            return True
        except psycopg2.OperationalError as e:
            logger.info(f"Waiting for database... (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
    
    logger.error("Could not connect to database")
    return False

def run_migrations(dsn):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cursor = conn.cursor()
    
    logger.info("Creating migrations tracking table if not exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    migration_files = sorted([
        f for f in os.listdir('/app/migrations')
        if f.endswith('.sql')
    ])
    
    for migration_file in migration_files:
        version = migration_file.replace('.sql', '')
        
        cursor.execute(
            "SELECT 1 FROM schema_migrations WHERE version = %s",
            (version,)
        )
        
        if cursor.fetchone():
            logger.info(f"Migration {version} already applied, skipping")
            continue
        
        logger.info(f"Applying migration {version}...")
        
        with open(f'/app/migrations/{migration_file}', 'r') as f:
            sql = f.read()
        
        try:
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,)
            )
            logger.info(f"Migration {version} applied successfully")
        except Exception as e:
            logger.error(f"Error applying migration {version}: {e}")
            conn.rollback()
            raise
    
    cursor.close()
    conn.close()
    logger.info("All migrations completed")

def main():
    dsn = os.getenv('PG_DSN', 'postgresql://oc:oc@db/opsconductor')
    
    if not wait_for_db(dsn):
        sys.exit(1)
    
    try:
        run_migrations(dsn)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
