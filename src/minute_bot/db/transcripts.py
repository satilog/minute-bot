"""Database operations for transcripts table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class TranscriptsDB:
    """Database operations for transcripts table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "transcripts"

    def create(
        self,
        meeting_id: str,
        text: str,
        start_time: float,
        end_time: float,
        speaker_id: Optional[str] = None,
        confidence: float = 1.0,
    ) -> dict:
        """Create a transcript segment."""
        data = {
            "meeting_id": meeting_id,
            "text": text,
            "start_time": start_time,
            "end_time": end_time,
            "speaker_id": speaker_id,
            "confidence": confidence,
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def create_batch(self, transcripts: list[dict]) -> list[dict]:
        """Create multiple transcript segments."""
        result = self.client.table(self.table).insert(transcripts).execute()
        return result.data or []

    def update_speaker(self, transcript_id: str, speaker_id: str) -> dict:
        """Update speaker for a transcript segment."""
        result = (
            self.client.table(self.table)
            .update({"speaker_id": speaker_id})
            .eq("id", transcript_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def get_unattributed_by_meeting(self, meeting_id: str) -> list[dict]:
        """Return transcript rows that have no speaker_id assigned yet."""
        result = (
            self.client.table(self.table)
            .select("id, start_time, end_time")
            .eq("meeting_id", meeting_id)
            .is_("speaker_id", "null")
            .order("start_time")
            .execute()
        )
        return result.data or []

    def update_speaker_batch(self, assignments: list[tuple[str, str]]) -> None:
        """Bulk-update speaker_id on transcript rows.

        Args:
            assignments: List of (transcript_id, speaker_id) pairs.
        """
        for transcript_id, speaker_id in assignments:
            self.update_speaker(transcript_id, speaker_id)

    def get_by_meeting(
        self,
        meeting_id: str,
        include_speaker: bool = True,
    ) -> list[dict]:
        """Get transcripts for a meeting."""
        query = (
            self.client.table(self.table)
            .select("*, speakers(speaker_label, speaker_name)" if include_speaker else "*")
            .eq("meeting_id", meeting_id)
            .order("start_time")
        )
        result = query.execute()
        return result.data or []
