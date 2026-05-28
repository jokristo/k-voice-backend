"""Suppression des fichiers audio après la période de rétention (économie stockage)."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Sermon, SermonStatus
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({SermonStatus.transcribing, SermonStatus.processing})


def audio_reference_time(sermon: Sermon) -> Optional[datetime]:
    """Horodatage de référence pour la rétention (upload ou repli)."""
    if sermon.audio_uploaded_at:
        return sermon.audio_uploaded_at
    if sermon.audio_url:
        return sermon.updated_at or sermon.created_at
    return None


def should_purge_sermon_audio(sermon: Sermon, now: Optional[datetime] = None) -> bool:
    if not settings.audio_retention_enabled:
        return False
    if not sermon.audio_url:
        return False
    if sermon.status in ACTIVE_STATUSES:
        return False

    ref = audio_reference_time(sermon)
    if not ref:
        return False

    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=settings.audio_retention_days)
    return ref < cutoff


def purge_sermon_audio_file(sermon: Sermon, db: Session) -> bool:
    """Supprime le fichier disque et efface les champs audio du sermon. Retourne True si purge faite."""
    if not sermon.audio_url:
        return False

    relative = sermon.audio_url.replace("/files/", "").lstrip("/")
    try:
        path = storage_service.get_file_path(relative)
        if path.is_file():
            path.unlink()
            logger.info("audio retention deleted file sermon_id=%s path=%s", sermon.id, relative)
    except OSError as e:
        logger.warning("audio retention unlink failed sermon_id=%s: %s", sermon.id, e)

    sermon.audio_url = None
    sermon.audio_size = None
    sermon.audio_duration = None
    sermon.audio_format = None
    sermon.audio_uploaded_at = None
    db.add(sermon)
    return True


def purge_expired_audio(db: Session, now: Optional[datetime] = None) -> int:
    """Parcourt les sermons avec audio et purge ceux dont la rétention est dépassée."""
    if not settings.audio_retention_enabled:
        return 0

    now = now or datetime.utcnow()
    candidates = (
        db.query(Sermon)
        .filter(Sermon.audio_url.isnot(None))
        .all()
    )
    purged = 0
    for sermon in candidates:
        if should_purge_sermon_audio(sermon, now=now):
            if purge_sermon_audio_file(sermon, db):
                purged += 1

    if purged:
        db.commit()
        logger.info(
            "audio retention run purged=%s retention_days=%s",
            purged,
            settings.audio_retention_days,
        )
    return purged
