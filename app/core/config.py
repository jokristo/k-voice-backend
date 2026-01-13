from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, BaseSettings, Field


class Settings(BaseSettings):
    app_name: str = "K-Voice API"
    environment: str = "development"
    database_url: str = "sqlite:///./kvoice.db"
    secret_key: str = "super-secret-key"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"
    cors_origins: List[AnyHttpUrl] | List[str] = ["http://localhost:3000"]
    storage_backend: str = "local"
    storage_local_path: str = "storage"
    max_upload_size_mb: int = 50
    rate_limit_enabled: bool = False
    default_ai_model: str = "whisper-v3"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
