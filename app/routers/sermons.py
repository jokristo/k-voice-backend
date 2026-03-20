from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps.auth import get_current_user, require_role
from app.models import RoleEnum, Sermon, SermonOutput, SermonStatus, User
from app.schemas import SermonCreate, SermonOut, SermonUpdate
from app.core.config import settings
from app.services import ai_service, media_service, nlp_service, storage_service

router = APIRouter()

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp3", "audio/mp4", "audio/x-wav"}


@router.get("", response_model=list[SermonOut])
def list_sermons(
    org_id: Optional[str] = Query(default=None),
    status_filter: Optional[SermonStatus] = Query(default=None, alias="status"),
    speaker: Optional[str] = Query(default=None),
    date: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Sermon)
    if org_id:
        query = query.filter(Sermon.organization_id == org_id)
    elif current_user.role != RoleEnum.admin:
        query = query.filter(Sermon.organization_id == current_user.organization_id)
    if status_filter:
        query = query.filter(Sermon.status == status_filter)
    if speaker:
        query = query.filter(Sermon.speaker.ilike(f"%{speaker}%"))
    if date:
        query = query.filter(Sermon.date == date.date())
    return query.all()


@router.post("", response_model=SermonOut, status_code=status.HTTP_201_CREATED)
def create_sermon(
    sermon_in: SermonCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.admin, RoleEnum.editor])),
):
    sermon = Sermon(**sermon_in.dict())
    db.add(sermon)
    db.commit()
    db.refresh(sermon)
    return sermon


@router.get("/{sermon_id}", response_model=SermonOut)
def get_sermon(sermon_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    if current_user.role != RoleEnum.admin and sermon.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return sermon


@router.patch("/{sermon_id}", response_model=SermonOut)
def update_sermon(
    sermon_id: str,
    sermon_in: SermonUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    for field, value in sermon_in.dict(exclude_unset=True).items():
        setattr(sermon, field, value)
    db.commit()
    db.refresh(sermon)
    return sermon


@router.post("/{sermon_id}/upload", response_model=SermonOut)
async def upload_sermon_audio(
    sermon_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.admin, RoleEnum.editor])),
):
    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported audio format")
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    relative_path, size = await storage_service.save_upload(file, subdir=sermon.organization_id)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size > max_bytes:
        storage_service.get_file_path(relative_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (>{settings.max_upload_size_mb}MB)",
        )

    duration = media_service.get_audio_duration_seconds(storage_service.get_file_path(relative_path))

    sermon.audio_url = storage_service.get_public_url(relative_path)
    sermon.audio_size = size
    sermon.audio_format = file.content_type
    sermon.audio_duration = duration
    db.commit()
    db.refresh(sermon)
    return sermon


def _run_transcription_job(sermon_id: str):
    db = SessionLocal()
    try:
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if not sermon or not sermon.audio_url:
            return
        sermon.status = SermonStatus.transcribing
        db.commit()

        file_path = ai_service.get_audio_path_from_sermon(storage_service.base_path, sermon)
        if not file_path or not file_path.exists():
            sermon.status = SermonStatus.failed
            db.commit()
            return

        result = ai_service.transcribe_audio(file_path)

        output = sermon.output or SermonOutput(sermon_id=sermon.id)
        output.transcript = result.get("transcript")
        output.transcript_words = result.get("transcript_words")
        output.word_count = result.get("word_count")
        output.processing_time = result.get("processing_time")
        output.estimated_read_time = nlp_service.estimate_read_time(output.word_count or 0)
        output.ai_model = settings.default_ai_model

        sermon.transcribed_at = datetime.utcnow()
        sermon.status = SermonStatus.processing
        sermon.output = output
        db.add(output)
        db.commit()
        db.refresh(sermon)
    except Exception:
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if sermon:
            sermon.status = SermonStatus.failed
            db.commit()
    finally:
        db.close()


@router.post("/{sermon_id}/transcribe")
def transcribe_sermon(
    sermon_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    if not sermon.audio_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio not uploaded")
    sermon.status = SermonStatus.transcribing
    db.commit()
    background_tasks.add_task(_run_transcription_job, sermon_id)
    return {"message": "Transcription started", "status": sermon.status}
