"""Database operations for meetings table."""

from datetime import datetime
from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class MeetingsDB:
    """Database operations for meetings table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "meetings"

    def create(
        self,
        session_id: str,
        title: Optional[str] = None,
        status: str = "active",
    ) -> dict:
        """Create a new meeting."""
        data = {
            "session_id": session_id,
            "title": title,
            "start_time": datetime.utcnow().isoformat(),
            "status": status,
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def get_by_id(self, meeting_id: str) -> Optional[dict]:
        """Get meeting by its UUID primary key."""
        result = (
            self.client.table(self.table)
            .select("*")
            .eq("id", meeting_id)
            .single()
            .execute()
        )
        return result.data

    def get_by_session_id(self, session_id: str) -> Optional[dict]:
        """Get meeting by session ID."""
        result = (
            self.client.table(self.table)
            .select("*")
            .eq("session_id", session_id)
            .single()
            .execute()
        )
        return result.data

    def update_status(self, meeting_id: str, status: str) -> dict:
        """Update meeting status."""
        data = {"status": status}
        if status == "completed":
            data["end_time"] = datetime.utcnow().isoformat()
        result = (
            self.client.table(self.table)
            .update(data)
            .eq("id", meeting_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def update_speaker_attribution_status(
        self, meeting_id: str, status: str
    ) -> dict:
        """Update the speaker attribution post-processing status.

        Valid values: 'pending' | 'processing' | 'completed' | 'failed'

        This is set by the background attribution job that runs after a meeting
        stops.  The UI should poll GET /meetings/<id> and use this field to
        decide whether to show a processing spinner or the final speaker view.
        """
        result = (
            self.client.table(self.table)
            .update({"speaker_attribution_status": status})
            .eq("id", meeting_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def update_graph_processing_status(self, meeting_id: str, status: str) -> dict:
        """Update the graph processing status.

        Valid values: 'pending' | 'processing' | 'completed' | 'failed'

        Set by the background job triggered when the user clicks "Process
        Transcript" on the frontend.
        """
        result = (
            self.client.table(self.table)
            .update({"graph_processing_status": status})
            .eq("id", meeting_id)
            .execute()
        )
        return result.data[0] if result.data else {}

    def list_recent(self, limit: int = 10) -> list[dict]:
        """List recent meetings."""
        result = (
            self.client.table(self.table)
            .select("*")
            .order("start_time", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
