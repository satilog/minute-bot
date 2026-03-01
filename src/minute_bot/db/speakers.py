"""Database operations for speakers table with pgvector embeddings."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class SpeakersDB:
    """Database operations for speakers table with pgvector embeddings."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "speakers"

    def create(
        self,
        meeting_id: str,
        speaker_label: str,
        speaker_name: Optional[str] = None,
        voice_embedding: Optional[list[float]] = None,
    ) -> dict:
        """Create a speaker record."""
        data = {
            "meeting_id": meeting_id,
            "speaker_label": speaker_label,
            "speaker_name": speaker_name or speaker_label,
            "voice_embedding": voice_embedding,
            "total_speaking_time": 0,
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def update_speaking_time(
        self,
        speaker_id: str,
        additional_seconds: float,
    ) -> dict:
        """Increment speaker's total speaking time."""
        current = (
            self.client.table(self.table)
            .select("total_speaking_time")
            .eq("id", speaker_id)
            .single()
            .execute()
        )
        current_time = (
            current.data.get("total_speaking_time", 0) if current.data else 0
        )

        result = (
            self.client.table(self.table)
            .update({"total_speaking_time": current_time + additional_seconds})
            .eq("id", speaker_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def update_name(self, speaker_id: str, name: str) -> dict:
        """Update speaker name."""
        result = (
            self.client.table(self.table)
            .update({"speaker_name": name})
            .eq("id", speaker_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def get_by_meeting(self, meeting_id: str) -> list[dict]:
        """Get speakers for a meeting."""
        result = (
            self.client.table(self.table)
            .select("*")
            .eq("meeting_id", meeting_id)
            .execute()
        )
        return result.data or []

    def find_by_embedding(
        self,
        embedding: list[float],
        threshold: float = 0.8,
        limit: int = 5,
    ) -> list[dict]:
        """Find similar speakers by voice embedding using pgvector."""
        result = self.client.rpc(
            "match_speakers",
            {
                "query_embedding": embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return result.data or []
