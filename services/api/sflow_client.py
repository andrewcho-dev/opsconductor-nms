import httpx
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SFlowClient:
    def __init__(self, sflow_url: str = "http://localhost:8008"):
        self.sflow_url = sflow_url.rstrip('/')
        
    async def get_interface_utilization(self, interface: str) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.sflow_url}/metric/ALL/{interface}/bytes/json"
                )
                if response.status_code == 200:
                    data = response.json()
                    return data
                return None
        except Exception as e:
            logger.warning(f"Failed to get sFlow data for {interface}: {e}")
            return None
    
    async def get_top_flows(self, limit: int = 100) -> List[Dict]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.sflow_url}/flows/json",
                    params={"maxFlows": limit}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, list) else []
                return []
        except Exception as e:
            logger.warning(f"Failed to get top flows from sFlow: {e}")
            return []
    
    async def get_flow_between_hosts(
        self, 
        src_ip: Optional[str] = None, 
        dst_ip: Optional[str] = None
    ) -> List[Dict]:
        try:
            params = {}
            if src_ip:
                params['ipsource'] = src_ip
            if dst_ip:
                params['ipdestination'] = dst_ip
                
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.sflow_url}/flows/json",
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, list) else []
                return []
        except Exception as e:
            logger.warning(f"Failed to get flows between {src_ip} and {dst_ip}: {e}")
            return []
    
    async def get_interface_counters(self) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.sflow_url}/dump/ALL/json")
                if response.status_code == 200:
                    return response.json()
                return {}
        except Exception as e:
            logger.warning(f"Failed to get interface counters from sFlow: {e}")
            return {}

sflow_client = SFlowClient()
