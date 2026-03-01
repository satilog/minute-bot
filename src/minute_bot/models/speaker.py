"""Speaker diarization models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from minute_bot.models.transcription import TranscriptionSegment


class SpeakerSegment(BaseModel):
    """Speaker turn segment from diarization."""

    session_id: str
    speaker_id: str
    start_time: float
    end_time: float
    confidence: float = 1.0


class SpeakerProfile(BaseModel):
    """Speaker profile with voice embedding reference."""

    speaker_id: str
    name: Optional[str] = None
    embedding_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DiarizedTranscript(BaseModel):
    """Combined transcription with speaker attribution."""

    session_id: str
    segments: list[TranscriptionSegment]
    speakers: list[SpeakerProfile] = []
