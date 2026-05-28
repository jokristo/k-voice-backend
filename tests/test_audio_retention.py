"""Tests unitaires — rétention audio 2 jours."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import SermonStatus
from app.services.audio_retention import (
    audio_reference_time,
    purge_expired_audio,
    should_purge_sermon_audio,
)


def _sermon(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", "s1")
    s.audio_url = kwargs.get("audio_url", "/files/org/test.mp3")
    s.audio_uploaded_at = kwargs.get("audio_uploaded_at")
    s.created_at = kwargs.get("created_at", datetime(2026, 1, 1))
    s.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1))
    s.status = kwargs.get("status", SermonStatus.completed)
    s.audio_size = 1000
    s.audio_duration = 60
    s.audio_format = "audio/mpeg"
    return s


@patch("app.services.audio_retention.settings")
def test_should_not_purge_when_transcribing(mock_settings):
    mock_settings.audio_retention_enabled = True
    mock_settings.audio_retention_days = 2
    s = _sermon(status=SermonStatus.transcribing, audio_uploaded_at=datetime.utcnow() - timedelta(days=5))
    assert should_purge_sermon_audio(s) is False


@patch("app.services.audio_retention.settings")
def test_should_purge_after_retention_days(mock_settings):
    mock_settings.audio_retention_enabled = True
    mock_settings.audio_retention_days = 2
    old = datetime.utcnow() - timedelta(days=3)
    s = _sermon(status=SermonStatus.completed, audio_uploaded_at=old)
    assert should_purge_sermon_audio(s) is True


@patch("app.services.audio_retention.settings")
def test_should_not_purge_recent_upload(mock_settings):
    mock_settings.audio_retention_enabled = True
    mock_settings.audio_retention_days = 2
    s = _sermon(status=SermonStatus.completed, audio_uploaded_at=datetime.utcnow())
    assert should_purge_sermon_audio(s) is False


@patch("app.services.audio_retention.settings")
def test_audio_reference_time_fallback_updated_at(mock_settings):
    mock_settings.audio_retention_enabled = True
    updated = datetime(2026, 5, 1, 12, 0, 0)
    s = _sermon(audio_uploaded_at=None, updated_at=updated)
    assert audio_reference_time(s) == updated


@patch("app.services.audio_retention.settings")
def test_purge_expired_audio_commits(mock_settings):
    mock_settings.audio_retention_enabled = True
    mock_settings.audio_retention_days = 2

    old_sermon = _sermon(
        audio_uploaded_at=datetime.utcnow() - timedelta(days=5),
        status=SermonStatus.completed,
    )
    recent = _sermon(
        id="s2",
        audio_uploaded_at=datetime.utcnow(),
        status=SermonStatus.completed,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [old_sermon, recent]

    with patch("app.services.audio_retention.storage_service") as storage:
        storage.get_file_path.return_value = MagicMock(is_file=lambda: True, unlink=MagicMock())
        n = purge_expired_audio(db)

    assert n == 1
    db.commit.assert_called_once()
    assert old_sermon.audio_url is None
    assert recent.audio_url is not None
