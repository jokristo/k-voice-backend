from fastapi import APIRouter

from app.services.media_service import ffmpeg_available

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "ffmpeg": ffmpeg_available()}
