"""Database operations for relationships table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class RelationshipsDB:
    """Database operations for relationships table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "relationships"

    def create(
        self,
        meeting_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a relationship and publish an SSE graph event."""
        data = {
            "meeting_id": meeting_id,
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "relationship_type": relationship_type,
            "metadata": metadata or {},
        }
        result = self.client.table(self.table).insert(data).execute()
        row = result.data[0] if result.data else {}
        # Publish real-time SSE event (best-effort — never raise)
        try:
            from minute_bot.pubsub.graph_publisher import publish_relationship
            publish_relationship(source_entity_id, target_entity_id, relationship_type)
        except Exception:
            pass
        return row

    def get_by_meeting(self, meeting_id: str) -> list[dict]:
        """Get relationships for a meeting."""
        result = (
            self.client.table(self.table)
            .select(
                "*, source:entities!source_entity_id(*), "
                "target:entities!target_entity_id(*)"
            )
            .eq("meeting_id", meeting_id)
            .execute()
        )
        return result.data or []

    def get_by_entity(self, entity_id: str) -> list[dict]:
        """Get relationships involving an entity."""
        result = (
            self.client.table(self.table)
            .select("*")
            .or_(f"source_entity_id.eq.{entity_id},target_entity_id.eq.{entity_id}")
            .execute()
        )
        return result.data or []
