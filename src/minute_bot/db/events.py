"""Database operations for events table."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class EventsDB:
    """Database operations for events table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "events"

    def create(
        self,
        meeting_id: str,
        event_type: str,
        description: str,
        timestamp: float,
        speaker_id: Optional[str] = None,
        confidence: float = 1.0,
        source_text: Optional[str] = None,
    ) -> dict:
        """Create an event and publish an SSE graph event."""
        from datetime import datetime, timezone

        data = {
            "meeting_id": meeting_id,
            "event_type": event_type,
            "description": description,
            "timestamp": timestamp,
            "speaker_id": speaker_id,
            "confidence": confidence,
            "source_text": source_text,
        }
        result = self.client.table(self.table).insert(data).execute()
        row = result.data[0] if result.data else {}
        # Publish real-time SSE event (best-effort — never raise)
        try:
            from minute_bot.pubsub.graph_publisher import publish_meeting_event
            publish_meeting_event(
                event_id=row.get("id", ""),
                event_type=event_type,
                description=description,
                timestamp=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
            )
        except Exception:
            pass
        return row

    def get_by_meeting(
        self,
        meeting_id: str,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """Get events for a meeting."""
        query = (
            self.client.table(self.table)
            .select("*, speakers(speaker_name)")
            .eq("meeting_id", meeting_id)
        )
        if event_type:
            query = query.eq("event_type", event_type)
        result = query.order("timestamp").execute()
        return result.data or []

    def get_action_items(self, meeting_id: str) -> list[dict]:
        """Get action items for a meeting."""
        return self.get_by_meeting(meeting_id, event_type="action_item")
