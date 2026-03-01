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
