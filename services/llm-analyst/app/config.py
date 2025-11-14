from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_base_url: str
    llm_model: str
    response_format: str = "json_schema"
    json_schema_path: str
    system_prompt_path: str
    batch_ms: int = 250
    max_evidence_items: int = 100
    max_patch_operations: int = 20
    max_flow_items: int = 80
    max_arp_items: int = 20
    state_server_url: str
    seed_gateway_ip: str | None = None
    seed_firewall_ip: str | None = None
    request_timeout: float = 60.0
    max_retries: int = 2

    @property
    def normalized_llm_url(self) -> str:
        return self.llm_base_url.rstrip("/")

    @property
    def state_patch_url(self) -> str:
        return f"{self.state_server_url.rstrip('/')}" + "/patch"


settings = Settings()
