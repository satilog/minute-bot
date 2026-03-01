"""Database layer for Minute Bot."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client
from minute_bot.db.meetings import MeetingsDB
from minute_bot.db.audio_files import AudioFilesDB
from minute_bot.db.transcripts import TranscriptsDB
from minute_bot.db.speakers import SpeakersDB
from minute_bot.db.events import EventsDB
from minute_bot.db.entities import EntitiesDB
from minute_bot.db.relationships import RelationshipsDB
from minute_bot.db.entity_mentions import EntityMentionsDB


class MinuteBotDB:
    """Unified database client for all Minute Bot tables."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.meetings = MeetingsDB(self.client)
        self.audio_files = AudioFilesDB(self.client)
        self.transcripts = TranscriptsDB(self.client)
        self.speakers = SpeakersDB(self.client)
        self.events = EventsDB(self.client)
        self.entities = EntitiesDB(self.client)
        self.relationships = RelationshipsDB(self.client)
        self.entity_mentions = EntityMentionsDB(self.client)

    def get_meeting_summary(self, meeting_id: str) -> dict:
        """Get full meeting summary with all related data."""
        meeting = self.meetings.get_by_session_id(meeting_id)
        if not meeting:
            return {}

        return {
            "meeting": meeting,
            "speakers": self.speakers.get_by_meeting(meeting["id"]),
            "transcripts": self.transcripts.get_by_meeting(meeting["id"]),
            "events": self.events.get_by_meeting(meeting["id"]),
            "entities": self.entities.get_by_meeting(meeting["id"]),
            "relationships": self.relationships.get_by_meeting(meeting["id"]),
        }


__all__ = [
    "get_supabase_client",
    "MinuteBotDB",
    "MeetingsDB",
    "AudioFilesDB",
    "TranscriptsDB",
    "SpeakersDB",
    "EventsDB",
    "EntitiesDB",
    "RelationshipsDB",
    "EntityMentionsDB",
]
