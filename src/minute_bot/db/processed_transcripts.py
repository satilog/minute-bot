"""Database operations for processed_transcripts table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class ProcessedTranscriptsDB:
    """Database operations for LLM-processed sentence-chunked transcripts."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "processed_transcripts"

    def create_batch(self, sentences: list[dict]) -> list[dict]:
        """Persist a batch of processed sentences."""
        result = self.client.table(self.table).insert(sentences).execute()
        return result.data or []

    def get_unattributed_by_meeting(self, meeting_id: str) -> list[dict]:
        """Return rows that have no speaker_id assigned yet."""
        result = (
            self.client.table(self.table)
            .select("id, start_time, end_time")
            .eq("meeting_id", meeting_id)
            .is_("speaker_id", "null")
            .order("start_time")
            .execute()
        )
        return result.data or []

    def update_speaker(self, row_id: str, speaker_id: str) -> dict:
        """Update speaker_id on a single processed transcript row."""
        result = (
            self.client.table(self.table)
            .update({"speaker_id": speaker_id})
            .eq("id", row_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def update_speaker_batch(self, assignments: list[tuple[str, str]]) -> None:
        """Bulk-update speaker_id.

        Args:
            assignments: List of (processed_transcript_id, speaker_id) pairs.
        """
        for row_id, speaker_id in assignments:
            self.update_speaker(row_id, speaker_id)

    def get_by_meeting(self, meeting_id: str) -> list[dict]:
        """Get processed transcripts for a meeting, ordered by time."""
        result = (
            self.client.table(self.table)
            .select("*, speakers(speaker_name)")
            .eq("meeting_id", meeting_id)
            .order("start_time")
            .execute()
        )
        return result.data or []
