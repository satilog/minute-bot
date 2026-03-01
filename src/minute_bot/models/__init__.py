"""Pydantic models for Minute Bot."""

from minute_bot.models.audio import AudioChunk, AudioSegment
from minute_bot.models.transcription import TranscriptionSegment, TranscriptionWord
from minute_bot.models.speaker import (
    DiarizedTranscript,
    SpeakerProfile,
    SpeakerSegment,
)
from minute_bot.models.events import EventType, MeetingEvent
from minute_bot.models.entities import Entity, EntityType, Relationship, RelationType
from minute_bot.models.session import MeetingSession, ProcessingStatus
from minute_bot.models.records import (
    AudioFileRecord,
    EntityMentionRecord,
    EntityRecord,
    EventRecord,
    GraphSnapshotRecord,
    MeetingRecord,
    RelationshipRecord,
    SpeakerRecord,
    TranscriptRecord,
)

__all__ = [
    # Audio
    "AudioChunk",
    "AudioSegment",
    # Transcription
    "TranscriptionSegment",
    "TranscriptionWord",
    # Speaker
    "DiarizedTranscript",
    "SpeakerProfile",
    "SpeakerSegment",
    # Events
    "EventType",
    "MeetingEvent",
    # Entities
    "Entity",
    "EntityType",
    "Relationship",
    "RelationType",
    # Session
    "MeetingSession",
    "ProcessingStatus",
    # Records
    "AudioFileRecord",
    "EntityMentionRecord",
    "EntityRecord",
    "EventRecord",
    "GraphSnapshotRecord",
    "MeetingRecord",
    "RelationshipRecord",
    "SpeakerRecord",
    "TranscriptRecord",
]
