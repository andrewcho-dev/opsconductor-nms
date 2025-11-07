import httpx
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class NetBoxDevice(BaseModel):
    name: str
    device_type: str
    site: str
    status: str = "active"
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    primary_ip: Optional[str] = None
    role: Optional[str] = None

class NetBoxCable(BaseModel):
    device_a: str
    interface_a: str
    device_b: str
    interface_b: str
    label: Optional[str] = None
    type: str = "cat6"

class NetBoxClient:
    def __init__(self, netbox_url: str, api_token: str):
        self.netbox_url = netbox_url.rstrip('/')
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def get_or_create_manufacturer(self, name: str) -> int:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.netbox_url}/api/dcim/manufacturers/",
                    headers=self.headers,
                    params={"name": name}
                )
                
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    if results:
                        return results[0]['id']
                
                create_response = await client.post(
                    f"{self.netbox_url}/api/dcim/manufacturers/",
                    headers=self.headers,
                    json={"name": name, "slug": name.lower().replace(' ', '-')}
                )
                
                if create_response.status_code in [200, 201]:
                    return create_response.json()['id']
                
                logger.error(f"Failed to create manufacturer: {create_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting/creating manufacturer {name}: {e}")
            return None
    
    async def get_or_create_device_type(self, manufacturer_id: int, model: str) -> int:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.netbox_url}/api/dcim/device-types/",
                    headers=self.headers,
                    params={"model": model}
                )
                
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    if results:
                        return results[0]['id']
                
                create_response = await client.post(
                    f"{self.netbox_url}/api/dcim/device-types/",
                    headers=self.headers,
                    json={
                        "manufacturer": manufacturer_id,
                        "model": model,
                        "slug": model.lower().replace(' ', '-').replace('/', '-')
                    }
                )
                
                if create_response.status_code in [200, 201]:
                    return create_response.json()['id']
                
                logger.error(f"Failed to create device type: {create_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting/creating device type {model}: {e}")
            return None
    
    async def get_or_create_site(self, name: str) -> int:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.netbox_url}/api/dcim/sites/",
                    headers=self.headers,
                    params={"name": name}
                )
                
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    if results:
                        return results[0]['id']
                
                create_response = await client.post(
                    f"{self.netbox_url}/api/dcim/sites/",
                    headers=self.headers,
                    json={"name": name, "slug": name.lower().replace(' ', '-')}
                )
                
                if create_response.status_code in [200, 201]:
                    return create_response.json()['id']
                
                logger.error(f"Failed to create site: {create_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting/creating site {name}: {e}")
            return None
    
    async def upsert_device(self, device: NetBoxDevice) -> Optional[Dict]:
        try:
            site_id = await self.get_or_create_site(device.site)
            if not site_id:
                logger.error(f"Failed to get/create site for device {device.name}")
                return None
            
            manufacturer_id = None
            device_type_id = None
            
            if device.manufacturer and device.model:
                manufacturer_id = await self.get_or_create_manufacturer(device.manufacturer)
                if manufacturer_id:
                    device_type_id = await self.get_or_create_device_type(
                        manufacturer_id, 
                        device.model
                    )
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.netbox_url}/api/dcim/devices/",
                    headers=self.headers,
                    params={"name": device.name}
                )
                
                device_data = {
                    "name": device.name,
                    "site": site_id,
                    "status": device.status,
                }
                
                if device_type_id:
                    device_data["device_type"] = device_type_id
                
                if device.role:
                    device_data["device_role"] = device.role
                
                if response.status_code == 200:
                    results = response.json().get('results', [])
                    if results:
                        device_id = results[0]['id']
                        update_response = await client.patch(
                            f"{self.netbox_url}/api/dcim/devices/{device_id}/",
                            headers=self.headers,
                            json=device_data
                        )
                        if update_response.status_code == 200:
                            return update_response.json()
                    else:
                        create_response = await client.post(
                            f"{self.netbox_url}/api/dcim/devices/",
                            headers=self.headers,
                            json=device_data
                        )
                        if create_response.status_code in [200, 201]:
                            return create_response.json()
                
                return None
        except Exception as e:
            logger.error(f"Error upserting device {device.name}: {e}")
            return None
    
    async def upsert_cable(self, cable: NetBoxCable) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                dev_a_response = await client.get(
                    f"{self.netbox_url}/api/dcim/devices/",
                    headers=self.headers,
                    params={"name": cable.device_a}
                )
                
                dev_b_response = await client.get(
                    f"{self.netbox_url}/api/dcim/devices/",
                    headers=self.headers,
                    params={"name": cable.device_b}
                )
                
                if dev_a_response.status_code != 200 or dev_b_response.status_code != 200:
                    logger.error("Failed to get devices for cable")
                    return None
                
                dev_a_results = dev_a_response.json().get('results', [])
                dev_b_results = dev_b_response.json().get('results', [])
                
                if not dev_a_results or not dev_b_results:
                    logger.error("Devices not found for cable")
                    return None
                
                dev_a_id = dev_a_results[0]['id']
                dev_b_id = dev_b_results[0]['id']
                
                if_a_response = await client.get(
                    f"{self.netbox_url}/api/dcim/interfaces/",
                    headers=self.headers,
                    params={"device_id": dev_a_id, "name": cable.interface_a}
                )
                
                if_b_response = await client.get(
                    f"{self.netbox_url}/api/dcim/interfaces/",
                    headers=self.headers,
                    params={"device_id": dev_b_id, "name": cable.interface_b}
                )
                
                if if_a_response.status_code != 200 or if_b_response.status_code != 200:
                    logger.error("Failed to get interfaces for cable")
                    return None
                
                if_a_results = if_a_response.json().get('results', [])
                if_b_results = if_b_response.json().get('results', [])
                
                if not if_a_results:
                    if_a_create = await client.post(
                        f"{self.netbox_url}/api/dcim/interfaces/",
                        headers=self.headers,
                        json={"device": dev_a_id, "name": cable.interface_a, "type": "other"}
                    )
                    if if_a_create.status_code in [200, 201]:
                        if_a_id = if_a_create.json()['id']
                    else:
                        return None
                else:
                    if_a_id = if_a_results[0]['id']
                
                if not if_b_results:
                    if_b_create = await client.post(
                        f"{self.netbox_url}/api/dcim/interfaces/",
                        headers=self.headers,
                        json={"device": dev_b_id, "name": cable.interface_b, "type": "other"}
                    )
                    if if_b_create.status_code in [200, 201]:
                        if_b_id = if_b_create.json()['id']
                    else:
                        return None
                else:
                    if_b_id = if_b_results[0]['id']
                
                cable_data = {
                    "a_terminations": [{"object_type": "dcim.interface", "object_id": if_a_id}],
                    "b_terminations": [{"object_type": "dcim.interface", "object_id": if_b_id}],
                    "type": cable.type,
                }
                
                if cable.label:
                    cable_data["label"] = cable.label
                
                create_response = await client.post(
                    f"{self.netbox_url}/api/dcim/cables/",
                    headers=self.headers,
                    json=cable_data
                )
                
                if create_response.status_code in [200, 201]:
                    return create_response.json()
                
                logger.error(f"Failed to create cable: {create_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error upserting cable: {e}")
            return None
