import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.deps.auth import get_current_user, require_role
from app.deps.scopes import assert_org_access
from app.models import Organization, RoleEnum, Sermon, SermonOutput, SermonStatus, User
from app.services import ai_service, brochure_service, nlp_service, storage_service
from app.services.billing.plans import plan_has_brochures
from app.services.billing.subscription_service import effective_billing_plan
from app.services.ai_service import TranscriptionError
from app.services.nlp_service import NLPProcessingError

router = APIRouter()
logger = logging.getLogger(__name__)


def _store_nlp_failure(sermon: Sermon, message: str, db: Session) -> None:
    sermon.status = SermonStatus.failed
    if sermon.output:
        meta = dict(sermon.output.nlp_metadata) if isinstance(sermon.output.nlp_metadata, dict) else {}
        meta["last_error"] = message[:500]
        sermon.output.nlp_metadata = meta
    db.commit()


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

        db.refresh(sermon)
        if sermon.status == SermonStatus.pending:
            logger.info("nlp process job ABORT sermon_id=%s reason=cancelled", sermon_id)
            return

        start = time.time()
        result = nlp_service.process_transcript(
            sermon.output.transcript, sermon.output.ai_model or ai_service.transcription_model_label()
        )

        db.refresh(sermon)
        if sermon.status == SermonStatus.pending:
            logger.info("nlp process job ABORT sermon_id=%s reason=cancelled_after_nlp", sermon_id)
            return
        output = sermon.output or SermonOutput(sermon_id=sermon.id)
        meta = dict(output.nlp_metadata) if isinstance(output.nlp_metadata, dict) else {}
        meta.pop("last_error", None)
        output.nlp_metadata = meta
        for field, value in result.items():
            if field == "nlp_metadata":
                merged = {**meta, **(value or {})}
                merged.pop("last_error", None)
                output.nlp_metadata = merged
            else:
                setattr(output, field, value)
        output.processing_time = int((time.time() - start) * 1000)

        org = db.query(Organization).filter(Organization.id == sermon.organization_id).first()
        recorder = db.query(User).filter(User.id == sermon.recorded_by_id).first()
        plan_key = effective_billing_plan(org) if org else "free"
        wants_brochure = plan_has_brochures(plan_key) or (
            recorder is not None and recorder.role == RoleEnum.super_admin
        )
        if wants_brochure:
            meta = output.nlp_metadata if isinstance(output.nlp_metadata, dict) else {}
            source = brochure_service.best_transcript_for_brochure(
                output.transcript or "",
                meta,
            )
            try:
                output.brochure_paragraphs = brochure_service.generate_brochure_paragraphs(source)
                meta = dict(output.nlp_metadata) if isinstance(output.nlp_metadata, dict) else {}
                meta.pop("brochure_error", None)
                output.nlp_metadata = meta
                logger.info(
                    "brochure generated sermon_id=%s paragraphs=%s",
                    sermon_id,
                    len(output.brochure_paragraphs or []),
                )
            except Exception as e:
                logger.warning("brochure FAIL sermon_id=%s: %s", sermon_id, e)
                meta = dict(output.nlp_metadata) if isinstance(output.nlp_metadata, dict) else {}
                meta["brochure_error"] = str(e)[:500]
                output.nlp_metadata = meta

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
    except NLPProcessingError as e:
        logger.warning("nlp process job FAIL sermon_id=%s NLPProcessingError: %s", sermon_id, e.message)
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if sermon:
            _store_nlp_failure(sermon, e.message, db)
    except Exception as e:
        logger.exception("nlp process job FAIL sermon_id=%s", sermon_id)
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if sermon:
            _store_nlp_failure(sermon, str(e), db)
    finally:
        db.close()


@router.post("/process/{sermon_id}")
def process_sermon(
    sermon_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.super_admin, RoleEnum.admin, RoleEnum.editor])),
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
    assert_org_access(current_user, sermon.organization_id)
    if sermon.status == SermonStatus.completed:
        logger.info("POST /ai/process skip sermon_id=%s already completed", sermon_id)
        return {"message": "Already completed", "status": sermon.status}
    if sermon.status == SermonStatus.failed:
        logger.info(
            "POST /ai/process retry after failure sermon_id=%s transcript_len=%s",
            sermon_id,
            len(sermon.output.transcript),
        )
    if sermon.status == SermonStatus.processing:
        logger.info("POST /ai/process skip sermon_id=%s already processing", sermon_id)
        return {"message": "Already processing", "status": sermon.status}
    logger.info(
        "POST /ai/process queued sermon_id=%s transcript_len=%s",
        sermon_id,
        len(sermon.output.transcript),
    )
    sermon.status = SermonStatus.processing
    db.commit()
    background_tasks.add_task(_process_sermon_job, sermon_id)
    return {"message": "Processing started", "status": sermon.status}
