"""Audio-related models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AudioChunk(BaseModel):
    """Audio chunk transmitted via Redis pub/sub."""

    session_id: str
    timestamp: datetime
    chunk_index: int
    sample_rate: int = 16000
    channels: int = 1
    format: str = "int16"
    audio_data: str  # Base64 encoded PCM


class AudioSegment(BaseModel):
    """A segment of audio with timing information."""

    start_time: float  # seconds
    end_time: float
    audio_data: Optional[str] = None  # Base64 encoded
