"""Database operations for the triplet_links table.

Triplet links are directed edges between triplets in the knowledge graph.
Three link types are maintained automatically by MinuteBotDB.create_triplet_links:
  - subject_match   — two triplets share the same subject_id
  - object_match    — two triplets share the same object_id
  - subject_object  — one triplet's subject is another's object (entity chain)
"""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class TripletLinksDB:
    """Database operations for the triplet_links table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "triplet_links"

    def create(
        self,
        from_id: str,
        to_id: str,
        link_type: str,
        weight: float = 1.0,
    ) -> dict:
        """Insert a directed link between two triplets.

        The table has a UNIQUE (from_id, to_id, link_type) constraint.
        Callers that tolerate duplicates should catch Exception.

        Args:
            from_id:   UUID of the source triplet.
            to_id:     UUID of the target triplet.
            link_type: 'subject_match', 'object_match', or 'subject_object'.
            weight:    Edge weight (default 1.0).

        Returns:
            The inserted row as a dict.
        """
        payload = {
            "from_id": from_id,
            "to_id": to_id,
            "link_type": link_type,
            "weight": weight,
        }
        result = self.client.table(self.table).insert(payload).execute()
        return result.data[0] if result.data else {}

    def get_by_triplet(self, triplet_id: str) -> list[dict]:
        """Get all links where the triplet appears as source or target.

        Args:
            triplet_id: UUID of the triplet to query.

        Returns:
            List of link rows.
        """
        result = (
            self.client.table(self.table)
            .select("*")
            .or_(f"from_id.eq.{triplet_id},to_id.eq.{triplet_id}")
            .execute()
        )
        return result.data or []
