"""Database operations for the triplets table.

The triplets table implements a temporal, vector-augmented knowledge graph
where each row is a subject-predicate-object fact annotated with:
  - provenance (source_meeting_id, source_turn_id, speaker_id, sequence)
  - temporal validity (valid_from / valid_until sequence numbers)
  - a 1536-dim embedding for semantic similarity search
"""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class TripletsDB:
    """Database operations for the triplets table."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "triplets"

    def insert(self, record: dict, embedding: list[float]) -> dict:
        """Insert a single triplet with its embedding vector.

        Args:
            record: Triplet fields — subject_text, subject_type, subject_id,
                    predicate, object_text, object_type, object_id, full_text,
                    source_turn_id, source_meeting_id, sequence, speaker_id,
                    valid_from. Optionally: event_type, confidence, valid_until.
            embedding: 1536-dim float vector from the embedding model.

        Returns:
            The inserted row as a dict (includes generated id and created_at).
        """
        payload = {**record, "embedding": embedding}
        result = self.client.table(self.table).insert(payload).execute()
        return result.data[0] if result.data else {}

    def search(
        self,
        query_embedding: list[float],
        threshold: float = 0.78,
        k: int = 10,
    ) -> list[dict]:
        """Semantic vector search using the search_triplets RPC.

        Args:
            query_embedding: 1536-dim query vector.
            threshold: Minimum cosine similarity (0–1). Rows below are excluded.
            k: Maximum number of results.

        Returns:
            List of matching triplet rows augmented with a ``similarity`` field.
        """
        result = self.client.rpc(
            "search_triplets",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": k,
            },
        ).execute()
        return result.data or []

    def get_snapshot(self, meeting_id: str, sequence: int) -> list[dict]:
        """Return all triplets valid at a given sequence point.

        Uses the get_snapshot RPC: returns every triplet where
        valid_from <= sequence AND (valid_until IS NULL OR valid_until > sequence).

        Args:
            meeting_id: Source meeting identifier.
            sequence: Sequence number to evaluate validity at.

        Returns:
            List of triplet rows ordered by sequence ascending.
        """
        result = self.client.rpc(
            "get_snapshot",
            {"p_meeting_id": meeting_id, "p_sequence": sequence},
        ).execute()
        return result.data or []

    def get_entity_context(self, entity_id: str) -> list[dict]:
        """Return all triplets referencing a given entity as subject or object.

        Args:
            entity_id: Canonical entity identifier (subject_id or object_id).

        Returns:
            List of triplet rows ordered by meeting and sequence.
        """
        result = self.client.rpc(
            "get_entity_context",
            {"p_entity_id": entity_id},
        ).execute()
        return result.data or []

    def get_open_tasks(self) -> list[dict]:
        """Return all open task-assignment triplets (predicate='assigned_to', valid_until IS NULL).

        Returns:
            List of triplet rows ordered by sequence descending (most recent first).
        """
        result = self.client.rpc("get_open_tasks", {}).execute()
        return result.data or []

    def close_prior(
        self,
        subject_id: str,
        predicate: str,
        new_object_id: str,
        at_sequence: int,
    ) -> None:
        """Invalidate superseded triplets when a fact changes.

        Sets valid_until = at_sequence on every open triplet (valid_until IS NULL)
        that shares subject_id and predicate but points to a different object.
        Preserves temporal history while marking old facts as no longer current.

        Typical use-cases: task reassignment, deadline change, status update.

        Args:
            subject_id:    Subject entity identifier.
            predicate:     Predicate being superseded (e.g. 'assigned_to').
            new_object_id: Object identifier of the new triplet — left open.
            at_sequence:   Sequence number at which old triplets are closed.
        """
        (
            self.client.table(self.table)
            .update({"valid_until": at_sequence})
            .eq("subject_id", subject_id)
            .eq("predicate", predicate)
            .neq("object_id", new_object_id)
            .is_("valid_until", "null")
            .execute()
        )
