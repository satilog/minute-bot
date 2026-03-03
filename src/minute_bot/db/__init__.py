"""Database layer for Minute Bot."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client
from minute_bot.db.meetings import MeetingsDB
from minute_bot.db.audio_files import AudioFilesDB
from minute_bot.db.transcripts import TranscriptsDB
from minute_bot.db.processed_transcripts import ProcessedTranscriptsDB
from minute_bot.db.speakers import SpeakersDB
from minute_bot.db.speaker_profiles import SpeakerProfilesDB
from minute_bot.db.events import EventsDB
from minute_bot.db.entities import EntitiesDB
from minute_bot.db.relationships import RelationshipsDB
from minute_bot.db.entity_mentions import EntityMentionsDB
from minute_bot.db.triplets import TripletsDB
from minute_bot.db.triplet_links import TripletLinksDB
from minute_bot.db.triplet_storage import TripletStorageDB


class MinuteBotDB:
    """Unified database client for all Minute Bot tables."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()

        # Core meeting tables
        self.meetings = MeetingsDB(self.client)
        self.audio_files = AudioFilesDB(self.client)
        self.transcripts = TranscriptsDB(self.client)
        self.processed_transcripts = ProcessedTranscriptsDB(self.client)
        self.speakers = SpeakersDB(self.client)
        self.speaker_profiles = SpeakerProfilesDB(self.client)

        # Knowledge graph tables
        self.events = EventsDB(self.client)
        self.entities = EntitiesDB(self.client)
        self.relationships = RelationshipsDB(self.client)
        self.entity_mentions = EntityMentionsDB(self.client)

        # Triplet store
        self.triplets = TripletsDB(self.client)
        self.triplet_links = TripletLinksDB(self.client)
        self.triplet_storage = TripletStorageDB(self.client)

    def get_meeting_summary(self, meeting_id: str) -> dict:
        """Get full meeting summary with all related data."""
        meeting = self.meetings.get_by_id(meeting_id)
        if not meeting:
            return {}

        return {
            "meeting": meeting,
            "speakers": self.speakers.get_by_meeting(meeting["id"]),
            "transcripts": self.transcripts.get_by_meeting(meeting["id"]),
            "processed_transcripts": self.processed_transcripts.get_by_meeting(meeting["id"]),
            "events": self.events.get_by_meeting(meeting["id"]),
            "entities": self.entities.get_by_meeting(meeting["id"]),
            "relationships": self.relationships.get_by_meeting(meeting["id"]),
        }

    def create_triplet_links(self, triplet: dict) -> None:
        """Auto-link a newly inserted triplet to related existing triplets.

        Creates three link types:
          subject_match  — another triplet shares the same subject_id
          object_match   — another triplet shares the same object_id
          subject_object — new subject_id equals another's object_id, or vice versa

        Duplicate links are silently skipped (unique constraint on the table).

        Args:
            triplet: Full triplet row as returned by triplets.insert().
                     Must contain 'id', 'subject_id', and 'object_id'.
        """
        new_id = triplet["id"]
        subject_id = triplet["subject_id"]
        object_id = triplet["object_id"]

        self._link_matching(new_id, "subject_id", subject_id, "subject_match")
        self._link_matching(new_id, "object_id", object_id, "object_match")
        self._link_matching(new_id, "object_id", subject_id, "subject_object")
        self._link_matching(new_id, "subject_id", object_id, "subject_object")

    def _link_matching(
        self, new_id: str, field: str, value: str, link_type: str
    ) -> None:
        """Query triplets matching a field/value and insert a link for each."""
        result = (
            self.client.table("triplets")
            .select("id")
            .eq(field, value)
            .neq("id", new_id)
            .execute()
        )
        for row in result.data or []:
            try:
                self.triplet_links.create(new_id, row["id"], link_type)
            except Exception:
                pass  # unique-constraint violation — link already exists


__all__ = [
    "get_supabase_client",
    "MinuteBotDB",
    "MeetingsDB",
    "AudioFilesDB",
    "TranscriptsDB",
    "ProcessedTranscriptsDB",
    "SpeakersDB",
    "SpeakerProfilesDB",
    "EventsDB",
    "EntitiesDB",
    "RelationshipsDB",
    "EntityMentionsDB",
    "TripletsDB",
    "TripletLinksDB",
    "TripletStorageDB",
]
