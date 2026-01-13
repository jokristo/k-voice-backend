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

router = APIRouter()


@router.post("/transcribe")
async def transcribe_endpoint(
    sermon_id: Optional[str] = None,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not sermon_id and not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide sermonId or file")

    if file:
        relative_path, _ = await storage_service.save_upload(file, subdir="uploads")
        audio_path = storage_service.get_file_path(relative_path)
        data = ai_service.transcribe_audio(audio_path)
        return data

    sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
    if not sermon or not sermon.audio_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon or audio not found")
    file_path = ai_service.get_audio_path_from_sermon(storage_service.base_path, sermon)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file missing")
    data = ai_service.transcribe_audio(file_path)
    return data


def _process_sermon_job(sermon_id: str):
    db = SessionLocal()
    try:
        sermon = db.query(Sermon).filter(Sermon.id == sermon_id).first()
        if not sermon:
            return
        if not sermon.output or not sermon.output.transcript:
            sermon.status = SermonStatus.failed
            db.commit()
            return
        sermon.status = SermonStatus.processing
        db.commit()

        start = time.time()
        result = nlp_service.process_transcript(sermon.output.transcript, sermon.output.ai_model or "whisper-v3")
        output = sermon.output or SermonOutput(sermon_id=sermon.id)
        for field, value in result.items():
            setattr(output, field, value)
        output.processing_time = int((time.time() - start) * 1000)
        sermon.processed_at = datetime.utcnow()
        sermon.status = SermonStatus.completed
        sermon.output = output
        db.add(output)
        db.commit()
    except Exception:
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sermon not found")
    if not sermon.output or not sermon.output.transcript:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcript missing")
    sermon.status = SermonStatus.processing
    db.commit()
    background_tasks.add_task(_process_sermon_job, sermon_id)
    return {"message": "Processing started", "status": sermon.status}
