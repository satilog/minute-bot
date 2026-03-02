"""Database operations for speaker_profiles table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class SpeakerProfilesDB:
    """Database operations for global speaker profiles (meeting-independent)."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "speaker_profiles"

    def create(
        self,
        name: str,
        voice_embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a speaker profile."""
        data = {
            "name": name,
            "voice_embedding": voice_embedding,
            "metadata": metadata or {},
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def list_all(self) -> list[dict]:
        """List all speaker profiles (excludes embeddings for bandwidth efficiency)."""
        result = (
            self.client.table(self.table)
            .select("id, name, metadata, created_at, updated_at")
            .execute()
        )
        return result.data or []

    def delete(self, profile_id: str) -> bool:
        """Delete a speaker profile by ID. Returns True if a row was deleted."""
        result = (
            self.client.table(self.table)
            .delete()
            .eq("id", profile_id)
            .execute()
        )
        return bool(result.data)

    def find_by_embedding(
        self,
        embedding: list[float],
        threshold: float = 0.7,
        limit: int = 1,
    ) -> list[dict]:
        """Find matching profiles by voice embedding similarity using pgvector."""
        result = self.client.rpc(
            "match_speaker_profiles",
            {
                "query_embedding": embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return result.data or []
