"""Database operations for entity_mentions table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class EntityMentionsDB:
    """Database operations for entity_mentions table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "entity_mentions"

    def create(
        self,
        entity_id: str,
        transcript_id: Optional[str] = None,
        event_id: Optional[str] = None,
        mention_text: str = "",
        context: Optional[str] = None,
    ) -> dict:
        """Create an entity mention."""
        data = {
            "entity_id": entity_id,
            "transcript_id": transcript_id,
            "event_id": event_id,
            "mention_text": mention_text,
            "context": context,
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def get_by_entity(self, entity_id: str) -> list[dict]:
        """Get mentions of an entity."""
        result = (
            self.client.table(self.table)
            .select("*, transcripts(*), events(*)")
            .eq("entity_id", entity_id)
            .execute()
        )
        return result.data or []
