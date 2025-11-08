from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime

router = APIRouter(prefix="/settings", tags=["settings"])

class PollingConfig(BaseModel):
    poll_networks: Optional[str] = ""
    skip_networks: Optional[str] = ""
    poll_enabled: Optional[bool] = True

class ConfigResponse(BaseModel):
    key: str
    value: str
    data_type: str
    description: Optional[str]
    updated_at: datetime

@router.get("/polling", response_model=PollingConfig)
async def get_polling_config():
    from main import db_pool
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT key, value FROM polling_config 
                WHERE key IN ('poll_networks', 'skip_networks', 'poll_enabled')
            """)
            
            config = {
                'poll_networks': '',
                'skip_networks': '',
                'poll_enabled': True
            }
            
            for row in rows:
                if row['key'] == 'poll_enabled':
                    config['poll_enabled'] = row['value'].lower() in ('true', '1', 'yes')
                else:
                    config[row['key']] = row['value']
            
            return PollingConfig(**config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/polling", response_model=PollingConfig)
async def update_polling_config(config: PollingConfig):
    from main import db_pool
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE polling_config 
                    SET value = $1, updated_at = NOW()
                    WHERE key = 'poll_networks'
                """, config.poll_networks or '')
                
                await conn.execute("""
                    UPDATE polling_config 
                    SET value = $1, updated_at = NOW()
                    WHERE key = 'skip_networks'
                """, config.skip_networks or '')
                
                await conn.execute("""
                    UPDATE polling_config 
                    SET value = $1, updated_at = NOW()
                    WHERE key = 'poll_enabled'
                """, 'true' if config.poll_enabled else 'false')
        
        return await get_polling_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/polling/all", response_model=Dict[str, ConfigResponse])
async def get_all_polling_config():
    from main import db_pool
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT key, value, data_type, description, updated_at 
                FROM polling_config 
                WHERE key LIKE 'poll_%' OR key LIKE 'skip_%'
                ORDER BY key
            """)
            
            result = {}
            for row in rows:
                result[row['key']] = ConfigResponse(
                    key=row['key'],
                    value=row['value'],
                    data_type=row['data_type'],
                    description=row['description'],
                    updated_at=row['updated_at']
                )
            
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
