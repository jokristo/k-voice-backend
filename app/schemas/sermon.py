from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from app.models import SermonStatus


class SermonOutputBase(BaseModel):
    transcript: Optional[str] = None
    transcript_words: Optional[Any] = None
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    main_themes: Optional[List[str]] = None
    key_verses: Optional[List[str]] = None
    references: Optional[List[str]] = None
    word_count: Optional[int] = None
    estimated_read_time: Optional[int] = None
    processing_time: Optional[int] = None
    ai_model: Optional[str] = None
    nlp_metadata: Optional[Any] = None
    brochure_paragraphs: Optional[Any] = None


class SermonOutputCreate(SermonOutputBase):
    sermon_id: str


class SermonOutputOut(SermonOutputBase):
    id: str
    sermon_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SermonBase(BaseModel):
    title: str
    speaker: str
    date: date
    description: Optional[str] = None
    audio_url: Optional[str] = None
    audio_size: Optional[int] = None
    audio_duration: Optional[int] = None
    audio_format: Optional[str] = None
    audio_uploaded_at: Optional[datetime] = None
    status: SermonStatus = SermonStatus.pending


class SermonCreate(SermonBase):
    """Internal / legacy — prefer SermonCreateIn + server-side org assignment."""
    organization_id: str
    recorded_by_id: str


class SermonCreateIn(SermonBase):
    """Client payload: org and recorder come from the authenticated user."""
    organization_id: Optional[str] = None


class SermonUpdate(BaseModel):
    title: Optional[str] = None
    speaker: Optional[str] = None
    date: Optional[date] = None
    description: Optional[str] = None
    audio_url: Optional[str] = None
    audio_size: Optional[int] = None
    audio_duration: Optional[int] = None
    audio_format: Optional[str] = None
    status: Optional[SermonStatus] = None
    transcribed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class SermonOut(SermonBase):
    id: str
    organization_id: str
    recorded_by_id: str
    created_at: datetime
    updated_at: datetime
    transcribed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    output: Optional[SermonOutputOut] = None

    model_config = ConfigDict(from_attributes=True)
