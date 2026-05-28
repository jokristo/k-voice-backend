import json
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
    max_upload_size_mb: int = 100
    # Fichiers audio : conservés sur disque N jours puis supprimés (transcript conservé en base)
    audio_retention_enabled: bool = True
    audio_retention_days: int = 2
    # Intervalle du job de purge en arrière-plan (secondes)
    audio_retention_sweep_interval_s: int = 3600
    # Limite API OpenAI Whisper (fichier unique)
    openai_whisper_max_file_mb: int = 25
    # Compression automatique (ffmpeg) vers MP3 mono avant transcription
    audio_compression_enabled: bool = True
    audio_compression_target_mb: int = 24
    audio_compression_min_kbps: int = 64
    audio_compression_floor_kbps: int = 24
    audio_compression_max_kbps: int = 128
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
    # Timeout HTTP par requête Whisper (secondes) — prédications longues / gros morceaux
    openai_transcription_timeout_s: int = 600
    openai_transcription_max_retries: int = 5
    # Résumé / NLP via Chat Completions (même OPENAI_API_KEY)
    openai_summary_model: str = "gpt-4o-mini"
    # openai | stub (stub = découpage naïf si pas de clé ou nlp_provider=stub)
    nlp_provider: Literal["openai", "stub"] = "openai"
    openai_nlp_max_transcript_chars: int = 100_000
    # Au-delà : pas de réécriture complète en étape 1 (évite timeout / JSON énorme)
    openai_nlp_skip_full_normalize_chars: int = 25_000
    openai_nlp_normalize_max_tokens: int = 4096
    openai_nlp_summarize_max_tokens: int = 4096
    # Texte max envoyé à l'étape résumé (prédications très longues)
    openai_nlp_summarize_max_input_chars: int = 45_000
    openai_nlp_json_retry_attempts: int = 2
    openai_nlp_timeout_s: int = 300
    openai_whisper_language: str = "fr"
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            raw = v.strip()
            if raw.startswith("["):
                return json.loads(raw)
            return [part.strip() for part in raw.split(",") if part.strip()]
        return v

    @field_validator("transcription_provider", mode="before")
    @classmethod
    def _normalize_transcription_provider(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("nlp_provider", mode="before")
    @classmethod
    def _normalize_nlp_provider(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
