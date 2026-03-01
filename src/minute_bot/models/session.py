"""Session and processing status models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from minute_bot.models.speaker import SpeakerProfile


class MeetingSession(BaseModel):
    """Metadata for a meeting recording session."""

    session_id: str
    title: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    participants: list[SpeakerProfile] = []
    status: str = "active"  # active, completed, failed


class ProcessingStatus(BaseModel):
    """Status of audio processing pipeline."""

    session_id: str
    audio_chunks_received: int = 0
    transcription_segments: int = 0
    speaker_segments: int = 0
    events_extracted: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
