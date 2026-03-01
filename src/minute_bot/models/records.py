"""Database record models for Supabase tables."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MeetingRecord(BaseModel):
    """Database record for meetings table."""

    id: Optional[str] = None
    session_id: str
    title: Optional[str] = None
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    status: str = "active"
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AudioFileRecord(BaseModel):
    """Database record for audio_files table."""

    id: Optional[str] = None
    meeting_id: str
    file_path: str
    duration_seconds: Optional[float] = None
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"
    file_size_bytes: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SpeakerRecord(BaseModel):
    """Database record for speakers table."""

    id: Optional[str] = None
    meeting_id: str
    speaker_label: str
    speaker_name: Optional[str] = None
    voice_embedding: Optional[list[float]] = None
    total_speaking_time: float = 0
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TranscriptRecord(BaseModel):
    """Database record for transcripts table."""

    id: Optional[str] = None
    meeting_id: str
    speaker_id: Optional[str] = None
    text: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    language: str = "en"
    words: list[dict] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EventRecord(BaseModel):
    """Database record for events table."""

    id: Optional[str] = None
    meeting_id: str
    speaker_id: Optional[str] = None
    event_type: str
    description: str
    timestamp: float
    confidence: float = 1.0
    source_text: Optional[str] = None
    requires_action: bool = False
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EntityRecord(BaseModel):
    """Database record for entities table."""

    id: Optional[str] = None
    meeting_id: str
    entity_type: str
    entity_name: str
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RelationshipRecord(BaseModel):
    """Database record for relationships table."""

    id: Optional[str] = None
    meeting_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    timestamp: Optional[float] = None
    metadata: dict = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EntityMentionRecord(BaseModel):
    """Database record for entity_mentions table."""

    id: Optional[str] = None
    entity_id: str
    transcript_id: Optional[str] = None
    event_id: Optional[str] = None
    mention_text: Optional[str] = None
    context: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphSnapshotRecord(BaseModel):
    """Database record for graph_snapshots table."""

    id: Optional[str] = None
    meeting_id: str
    snapshot_time: float
    snapshot_data: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)
