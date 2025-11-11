from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    api_port: int = 8080
    ui_ws_origin: str = "*"

    @property
    def async_db_url(self) -> str:
        if self.db_url.startswith("postgresql+asyncpg"):
            return self.db_url
        if self.db_url.startswith("postgresql://"):
            return self.db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.db_url


settings = Settings()
