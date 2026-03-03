"""Database operations for entities table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class EntitiesDB:
    """Database operations for entities table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "entities"

    def create(
        self,
        meeting_id: str,
        entity_type: str,
        entity_name: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create an entity and publish an SSE graph event."""
        data = {
            "meeting_id": meeting_id,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "metadata": metadata or {},
        }
        result = self.client.table(self.table).insert(data).execute()
        row = result.data[0] if result.data else {}
        # Publish real-time SSE event (best-effort — never raise)
        try:
            from minute_bot.pubsub.graph_publisher import publish_entity
            publish_entity(row.get("id", ""), entity_type, entity_name)
        except Exception:
            pass
        return row

    def get_or_create(
        self,
        meeting_id: str,
        entity_type: str,
        entity_name: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Get existing entity or create new one."""
        existing = (
            self.client.table(self.table)
            .select("*")
            .eq("meeting_id", meeting_id)
            .eq("entity_type", entity_type)
            .eq("entity_name", entity_name)
            .execute()
        )
        if existing.data:
            return existing.data[0]
        return self.create(meeting_id, entity_type, entity_name, metadata)

    def get_by_meeting(
        self,
        meeting_id: str,
        entity_type: Optional[str] = None,
    ) -> list[dict]:
        """Get entities for a meeting."""
        query = (
            self.client.table(self.table).select("*").eq("meeting_id", meeting_id)
        )
        if entity_type:
            query = query.eq("entity_type", entity_type)
        result = query.execute()
        return result.data or []
