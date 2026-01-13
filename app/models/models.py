from datetime import date, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class RoleEnum(str, Enum):
    admin = "admin"
    editor = "editor"
    member = "member"


class SermonStatus(str, Enum):
    pending = "pending"
    transcribing = "transcribing"
    processing = "processing"
    completed = "completed"
    failed = "failed"


def _generate_uuid() -> str:
    return str(uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=_generate_uuid)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    logo = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    sermons = relationship("Sermon", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(SqlEnum(RoleEnum), default=RoleEnum.member, nullable=False)
    avatar = Column(String)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organization = relationship("Organization", back_populates="users")
    sermons = relationship("Sermon", back_populates="recorded_by")


class Sermon(Base):
    __tablename__ = "sermons"

    id = Column(String, primary_key=True, default=_generate_uuid)
    title = Column(String, nullable=False)
    speaker = Column(String, nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    description = Column(Text)
    audio_url = Column(String)
    audio_size = Column(Integer)
    audio_duration = Column(Integer)
    audio_format = Column(String)
    status = Column(SqlEnum(SermonStatus), default=SermonStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    transcribed_at = Column(DateTime)
    processed_at = Column(DateTime)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_by_id = Column(String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    organization = relationship("Organization", back_populates="sermons")
    recorded_by = relationship("User", back_populates="sermons")
    output = relationship("SermonOutput", uselist=False, back_populates="sermon", cascade="all, delete-orphan")


class SermonOutput(Base):
    __tablename__ = "sermon_outputs"

    id = Column(String, primary_key=True, default=_generate_uuid)
    sermon_id = Column(String, ForeignKey("sermons.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    transcript = Column(Text)
    transcript_words = Column(JSON)
    summary = Column(Text)
    key_points = Column(JSON)
    main_themes = Column(JSON)
    key_verses = Column(JSON)
    references = Column(JSON)
    word_count = Column(Integer)
    estimated_read_time = Column(Integer)
    processing_time = Column(Integer)
    ai_model = Column(String, default="whisper-v3")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sermon = relationship("Sermon", back_populates="output")
