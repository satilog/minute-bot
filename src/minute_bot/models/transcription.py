"""Transcription-related models."""

from typing import Optional

from pydantic import BaseModel


class TranscriptionWord(BaseModel):
    """Individual word with timing."""

    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0


class TranscriptionSegment(BaseModel):
    """Transcribed segment with timing and optional speaker."""

    session_id: str
    segment_id: str
    text: str
    start_time: float
    end_time: float
    words: list[TranscriptionWord] = []
    language: str = "en"
    confidence: float = 1.0
    speaker_id: Optional[str] = None
