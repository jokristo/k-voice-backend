from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/limits")
def upload_limits():
    return {
        "max_upload_size_mb": settings.max_upload_size_mb,
        "whisper_max_file_mb": settings.openai_whisper_max_file_mb,
        "transcription_provider": settings.transcription_provider,
        "audio_compression_enabled": settings.audio_compression_enabled,
        "audio_compression_target_mb": settings.audio_compression_target_mb,
        "audio_compression_min_kbps": settings.audio_compression_min_kbps,
        "audio_compression_floor_kbps": settings.audio_compression_floor_kbps,
        "audio_compression_max_kbps": settings.audio_compression_max_kbps,
        "audio_retention_enabled": settings.audio_retention_enabled,
        "audio_retention_days": settings.audio_retention_days,
    }
