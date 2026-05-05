import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps.auth import get_current_user, require_role
from app.models import RoleEnum, Sermon, SermonOutput, SermonStatus, User
from app.services import ai_service, nlp_service, storage_service
from app.services.ai_service import TranscriptionError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/transcribe")
async def transcribe_endpoint(
    sermon_id: Optional[str] = None,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not sermon_id and not file:
        logger.warning("POST /ai/transcribe missing sermon_id and file")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide sermonId or file")

    if file:
        logger.info("POST /ai/transcribe direct file filename=%r", file.filename)
        relative_path, _ = await storage_service.save_upload(file, subdir="uploads")
        audio_path = storage_service.get_file_path(relative_path)
        try:
            data = ai_service.transcribe_audio(audio_path)
        except TranscriptionError as e:
            logger.warning("POST /ai/transcribe file TranscriptionError: %s", e.message)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
        logger.info("POST /ai/transcribe file ok word_count=%s", data.get("word_count"))
        return data

    logger.info("POST /ai/transcribe sermon_id=%s", sermon_id)
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon or not sermon.audio_url:
        logger.warning(
            "POST /ai/transcribe 404 sermon_id=%s found=%s audio_url=%s",
            sermon_id,
            bool(sermon),
            getattr(sermon, "audio_url", None),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon or audio not found")
    file_path = ai_service.get_audio_path_from_sermon(storage_service.base_path, sermon)
    if not file_path or not Path(file_path).exists():
        logger.warning(
            "POST /ai/transcribe sermon_id=%s file_path=%s exists=%s",
            sermon_id,
            file_path,
            Path(file_path).exists() if file_path else False,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file missing")
    try:
        data = ai_service.transcribe_audio(file_path)
    except TranscriptionError as e:
        logger.warning("POST /ai/transcribe sermon TranscriptionError: %s", e.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message) from e
    logger.info("POST /ai/transcribe sermon ok sermon_id=%s word_count=%s", sermon_id, data.get("word_count"))
    return data


def _process_sermon_job(sermon_id: str):
    db = SessionLocal()
    logger.info("nlp process job START sermon_id=%s", sermon_id)
    try:
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if not sermon:
            logger.error("nlp process job ABORT sermon_id=%s reason=no_sermon", sermon_id)
            return
        if not sermon.output or not sermon.output.transcript:
            tlen = len((sermon.output.transcript or "")) if sermon.output else 0
            logger.error(
                "nlp process job ABORT sermon_id=%s reason=no_transcript has_output=%s transcript_len=%s",
                sermon_id,
                sermon.output is not None,
                tlen,
            )
            sermon.status = SermonStatus.failed
            db.commit()
            return
        sermon.status = SermonStatus.processing
        db.commit()

        start = time.time()
        result = nlp_service.process_transcript(
            sermon.output.transcript, sermon.output.ai_model or ai_service.transcription_model_label()
        )
        output = sermon.output or SermonOutput(sermon_id=sermon.id)
        for field, value in result.items():
            setattr(output, field, value)
        output.processing_time = int((time.time() - start) * 1000)
        sermon.processed_at = datetime.utcnow()
        sermon.status = SermonStatus.completed
        sermon.output = output
        db.add(output)
        db.commit()
        logger.info(
            "nlp process job DONE sermon_id=%s status=%s summary_len=%s",
            sermon_id,
            sermon.status,
            len((output.summary or "")),
        )
    except Exception:
        logger.exception("nlp process job FAIL sermon_id=%s", sermon_id)
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if sermon:
            sermon.status = SermonStatus.failed
            db.commit()
    finally:
        db.close()


@router.post("/process/{sermon_id}")
def process_sermon(
    sermon_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_role([RoleEnum.admin, RoleEnum.editor])),
):
    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon:
        logger.warning("POST /ai/process 404 sermon_id=%s", sermon_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    if not sermon.output or not sermon.output.transcript:
        tlen = len((sermon.output.transcript or "")) if sermon.output else 0
        logger.warning(
            "POST /ai/process 400 sermon_id=%s detail=Transcript missing audio_url=%s has_output=%s "
            "transcript_len=%s sermon_status=%s — run POST .../transcribe and wait for transcript first",
            sermon_id,
            sermon.audio_url,
            sermon.output is not None,
            tlen,
            sermon.status,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcript missing")
    logger.info(
        "POST /ai/process queued sermon_id=%s transcript_len=%s",
        sermon_id,
        len(sermon.output.transcript),
    )
    sermon.status = SermonStatus.processing
    db.commit()
    background_tasks.add_task(_process_sermon_job, sermon_id)
    return {"message": "Processing started", "status": sermon.status}
