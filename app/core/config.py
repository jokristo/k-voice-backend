from functools import lru_cache
from typing import List, Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
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
    # gemini | openai | local (faster-whisper sur la machine)
    transcription_provider: Literal["gemini", "openai", "local"] = "gemini"
    # Surcharge via DEFAULT_AI_MODEL dans .env si quota / disponibilité différente selon le projet.
    default_ai_model: str = "gemini-2.0-flash"
    gemini_api_key: str = ""
    gemini_file_ready_timeout_s: int = 300
    openai_api_key: str = ""
    # ex. whisper-1 (voir doc OpenAI Speech-to-Text)
    openai_transcription_model: str = "whisper-1"
    # --- Transcription locale (faster-whisper) : voir TRANSCRIPTION_PROVIDER=local
    # tiny, base, small, medium, large-v2, large-v3, etc.
    local_whisper_model_size: str = "base"
    # auto | cpu | cuda
    local_whisper_device: str = "auto"
    # Vide = int8 (cpu) ou float16 (cuda). Sinon ex. int8_float16, float32
    local_whisper_compute_type: str = ""
    # Code langue ISO (ex. fr) ; vide = détection automatique
    local_whisper_language: str = ""
    # Cache des poids Hugging Face (optionnel)
    local_whisper_download_root: str = ""

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def _normalize_transcription_provider(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
