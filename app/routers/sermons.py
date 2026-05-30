import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps.auth import get_current_user, require_role
from app.deps.scopes import assert_org_access, is_super_admin, resolve_sermon_organization_id
from app.models import Organization, RoleEnum, Sermon, SermonOutput, SermonStatus, User
from app.schemas import SermonCreateIn, SermonOut, SermonUpdate
from app.core.config import settings
from app.services import ai_service, media_service, nlp_service, storage_service
from app.services.billing.subscription_service import assert_can_create_sermon
from app.services.ai_service import TranscriptionError
from app.services.media_service import MediaProcessingError, compress_audio_for_storage

router = APIRouter()
logger = logging.getLogger(__name__)

# video/webm: navigateurs (MediaRecorder) envoient souvent ce type pour un enregistrement « audio ».
ALLOWED_AUDIO_TYPES = frozenset(
    {
        "audio/webm",
        "video/webm",
        "audio/ogg",
        "audio/mpeg",
        "audio/wav",
        "audio/mp3",
        "audio/mp4",
        "audio/x-wav",
        "audio/opus",
        "audio/flac",
        "audio/aac",
        "audio/x-m4a",
    }
)

_EXT_ALLOWED = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}


def _normalized_upload_mime(file: UploadFile) -> Optional[str]:
    """MIME de base sans paramètres (ex. audio/webm; codecs=opus -> audio/webm)."""
    if not file.content_type:
        return None
    return file.content_type.split(";", 1)[0].strip().lower()


def _effective_audio_mime(file: UploadFile) -> Optional[str]:
    base = _normalized_upload_mime(file)
    if base in ALLOWED_AUDIO_TYPES:
        return base
    if base in ("application/octet-stream", "binary/octet-stream") or base is None:
        if file.filename:
            ext = Path(file.filename).suffix.lower()
            if ext in _EXT_ALLOWED:
                return _EXT_ALLOWED[ext]
    return base


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
        if not is_super_admin(current_user) and org_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        query = query.filter(Sermon.organization_id == org_id)
    elif not is_super_admin(current_user):
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
    sermon_in: SermonCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    org_id = resolve_sermon_organization_id(current_user, sermon_in.organization_id)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    try:
        assert_can_create_sermon(db, org)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(e)) from e
    payload = sermon_in.dict(exclude={"organization_id"})
    sermon = Sermon(
        **payload,
        organization_id=org_id,
        recorded_by_id=current_user.id,
    )
    db.add(sermon)
    db.commit()
    db.refresh(sermon)
    logger.info(
        "sermon created id=%s title=%r status=%s audio_url=%s has_output=%s",
        sermon.id,
        sermon.title,
        sermon.status,
        sermon.audio_url,
        sermon.output is not None,
    )
    return sermon


@router.get("/{sermon_id}", response_model=SermonOut)
def get_sermon(sermon_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    assert_org_access(current_user, sermon.organization_id)
    return sermon


@router.patch("/{sermon_id}", response_model=SermonOut)
def update_sermon(
    sermon_id: str,
    sermon_in: SermonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    assert_org_access(current_user, sermon.organization_id)
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
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    logger.info(
        "upload start sermon_id=%s filename=%r declared_content_type=%r",
        sermon_id,
        file.filename,
        file.content_type,
    )
    effective_mime = _effective_audio_mime(file)
    if effective_mime not in ALLOWED_AUDIO_TYPES:
        logger.warning(
            "upload rejected sermon_id=%s effective_mime=%r raw_ct=%r",
            sermon_id,
            effective_mime,
            file.content_type,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format (content-type={file.content_type!r})",
        )
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        logger.warning("upload 404 sermon_id=%s (sermon not found)", sermon_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    assert_org_access(current_user, sermon.organization_id)
    relative_path, size = await storage_service.save_upload(file, subdir=sermon.organization_id)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size > max_bytes:
        storage_service.get_file_path(relative_path).unlink(missing_ok=True)
        logger.warning("upload too large sermon_id=%s size_bytes=%s", sermon_id, size)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (>{settings.max_upload_size_mb}MB)",
        )

    stored_path = storage_service.get_file_path(relative_path)
    try:
        compressed_path, was_compressed = compress_audio_for_storage(stored_path)
        if was_compressed:
            relative_path = compressed_path.relative_to(storage_service.base_path).as_posix()
            size = compressed_path.stat().st_size
            effective_mime = "audio/mpeg"
            stored_path = compressed_path
            logger.info(
                "upload compressed sermon_id=%s new_relative=%s size=%s",
                sermon_id,
                relative_path,
                size,
            )
    except MediaProcessingError as e:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e

    duration = media_service.get_audio_duration_seconds(stored_path)

    sermon.audio_url = storage_service.get_public_url(relative_path)
    sermon.audio_size = size
    sermon.audio_format = effective_mime
    sermon.audio_duration = duration
    sermon.audio_uploaded_at = datetime.utcnow()
    db.commit()
    db.refresh(sermon)
    logger.info(
        "upload ok sermon_id=%s audio_url=%s size=%s duration_s=%s mime=%s",
        sermon_id,
        sermon.audio_url,
        size,
        duration,
        effective_mime,
    )
    return sermon


def _run_transcription_job(sermon_id: str):
    db = SessionLocal()
    logger.info("transcription job START sermon_id=%s", sermon_id)
    try:
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if not sermon:
            logger.error("transcription job ABORT sermon_id=%s reason=no_sermon_row", sermon_id)
            return
        if not sermon.audio_url:
            logger.error(
                "transcription job ABORT sermon_id=%s reason=no_audio_url (call POST .../upload first)",
                sermon_id,
            )
            return
        sermon.status = SermonStatus.transcribing
        db.commit()

        file_path = ai_service.get_audio_path_from_sermon(storage_service.base_path, sermon)
        if not file_path:
            logger.error("transcription job ABORT sermon_id=%s reason=file_path_none audio_url=%r", sermon_id, sermon.audio_url)
            sermon.status = SermonStatus.failed
            db.commit()
            return
        if not file_path.exists():
            logger.error(
                "transcription job ABORT sermon_id=%s reason=file_missing path=%s",
                sermon_id,
                file_path,
            )
            sermon.status = SermonStatus.failed
            db.commit()
            return

        db.refresh(sermon)
        if sermon.status == SermonStatus.pending:
            logger.info("transcription job ABORT sermon_id=%s reason=cancelled", sermon_id)
            return

        logger.info("transcription job RUN sermon_id=%s file=%s provider=%s", sermon_id, file_path, settings.transcription_provider)
        result = ai_service.transcribe_audio(file_path)

        db.refresh(sermon)
        if sermon.status == SermonStatus.pending:
            logger.info("transcription job ABORT sermon_id=%s reason=cancelled_after_ai", sermon_id)
            return
        transcript_preview = (result.get("transcript") or "")[:120]
        logger.info(
            "transcription job AI_OK sermon_id=%s word_count=%s preview=%r",
            sermon_id,
            result.get("word_count"),
            transcript_preview,
        )

        output = sermon.output or SermonOutput(sermon_id=sermon.id)
        output.transcript = result.get("transcript")
        output.transcript_words = result.get("transcript_words")
        output.word_count = result.get("word_count")
        output.processing_time = result.get("processing_time")
        output.estimated_read_time = nlp_service.estimate_read_time(output.word_count or 0)
        output.ai_model = ai_service.transcription_model_label()

        sermon.transcribed_at = datetime.utcnow()
        sermon.status = SermonStatus.processing
        sermon.output = output
        db.add(output)
        db.commit()
        db.refresh(sermon)
        logger.info(
            "transcription job DONE sermon_id=%s status=%s has_transcript=%s — chaining NLP",
            sermon_id,
            sermon.status,
            bool(output.transcript),
        )
        from app.routers.ai import _process_sermon_job

        _process_sermon_job(sermon_id)
    except TranscriptionError as e:
        logger.warning("transcription job FAIL sermon_id=%s TranscriptionError: %s", sermon_id, e.message)
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if sermon:
            sermon.status = SermonStatus.failed
            db.commit()
    except Exception:
        logger.exception("transcription job FAIL sermon_id=%s unexpected", sermon_id)
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
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        logger.warning("transcribe HTTP 404 sermon_id=%s", sermon_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    if not sermon.audio_url:
        logger.warning(
            "transcribe HTTP 400 sermon_id=%s reason=audio_not_uploaded status=%s audio_url=%s",
            sermon_id,
            sermon.status,
            sermon.audio_url,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio not uploaded")
    file_path = ai_service.get_audio_path_from_sermon(storage_service.base_path, sermon)
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier audio introuvable (peut-être supprimé après la période de rétention). Réimportez l'audio.",
        )
    assert_org_access(current_user, sermon.organization_id)
    if sermon.status in (SermonStatus.transcribing, SermonStatus.processing):
        return {"message": "Already in progress", "status": sermon.status}
    if sermon.status in (SermonStatus.failed, SermonStatus.pending):
        logger.info("transcribe retry sermon_id=%s previous_status=%s", sermon_id, sermon.status)
    logger.info(
        "transcribe queued sermon_id=%s audio_url=%s current_status=%s",
        sermon_id,
        sermon.audio_url,
        sermon.status,
    )
    sermon.status = SermonStatus.transcribing
    db.commit()
    background_tasks.add_task(_run_transcription_job, sermon_id)
    return {"message": "Transcription started", "status": sermon.status}


def _assert_sermon_access(sermon: Sermon, current_user: User) -> None:
    assert_org_access(current_user, sermon.organization_id)


@router.post("/{sermon_id}/cancel")
def cancel_sermon_processing(
    sermon_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    _assert_sermon_access(sermon, current_user)
    if sermon.status not in (SermonStatus.transcribing, SermonStatus.processing):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only in-progress transcriptions can be cancelled",
        )
    sermon.status = SermonStatus.pending
    db.commit()
    db.refresh(sermon)
    logger.info("sermon cancel sermon_id=%s new_status=%s", sermon_id, sermon.status)
    return {"message": "Transcription cancelled", "status": sermon.status}


@router.delete("/{sermon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sermon(
    sermon_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    _assert_sermon_access(sermon, current_user)
    if sermon.audio_url:
        relative = sermon.audio_url.replace("/files/", "")
        try:
            storage_service.get_file_path(relative).unlink(missing_ok=True)
        except OSError:
            logger.warning("delete sermon_id=%s could not unlink audio %s", sermon_id, relative)
    db.delete(sermon)
    db.commit()
    logger.info("sermon deleted sermon_id=%s", sermon_id)
