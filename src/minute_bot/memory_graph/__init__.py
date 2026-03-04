"""Memory graph module — the single entry point for all knowledge-graph operations.

This module encapsulates everything related to the meeting memory graph:
  - LLM-based extraction of events, entities, and relationships
  - Temporal triplet store (subject-predicate-object facts with vector embeddings)
  - Triplet link graph (subject_match, object_match, subject_object edges)
  - Storage uploads for audio and transcript artefacts

Usage
-----
# Trigger post-meeting graph processing (called from the API layer):
from minute_bot.memory_graph import process_meeting_async
process_meeting_async(meeting_id)

# Query the graph for a meeting:
from minute_bot.memory_graph import MemoryGraph
graph = MemoryGraph()
entities      = graph.get_entities(meeting_id)
events        = graph.get_events(meeting_id)
relationships = graph.get_relationships(meeting_id)

# Triplet store:
triplet = graph.insert_triplet(record, embedding)
graph.create_triplet_links(triplet)
results = graph.search_triplets(query_embedding)
snapshot = graph.get_snapshot(meeting_id, sequence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Public API: process_meeting_async
# ---------------------------------------------------------------------------

def process_meeting_async(meeting_id: str) -> None:
    """Trigger LLM transcript cleanup and graph extraction in a background thread.

    This is the entry point called by POST /meetings/<id>/process.
    Progress is written to meeting.graph_processing_status so the UI can poll.

    Args:
        meeting_id: UUID of the completed meeting to process.
    """
    from minute_bot.memory_graph.processing import process_meeting_async as _run
    _run(meeting_id)


# ---------------------------------------------------------------------------
# Public API: MemoryGraph
# ---------------------------------------------------------------------------

class MemoryGraph:
    """Unified interface for all memory-graph read and write operations.

    Wraps the database layer so callers never import from ``minute_bot.db``
    directly for graph-related work.  Create one instance per request or
    reuse across a processing session.
    """

    def __init__(self):
        from minute_bot.db import MinuteBotDB
        self._db = MinuteBotDB()

    # ------------------------------------------------------------------
    # Knowledge graph — events, entities, relationships
    # ------------------------------------------------------------------

    def get_entities(self, meeting_id: str, entity_type: str | None = None) -> list[dict]:
        """Return entities extracted from a meeting."""
        return self._db.entities.get_by_meeting(meeting_id, entity_type=entity_type)

    def get_events(self, meeting_id: str, event_type: str | None = None) -> list[dict]:
        """Return events extracted from a meeting."""
        return self._db.events.get_by_meeting(meeting_id, event_type=event_type)

    def get_relationships(self, meeting_id: str) -> list[dict]:
        """Return relationships extracted from a meeting, with entity join."""
        return self._db.relationships.get_by_meeting(meeting_id)

    def get_action_items(self, meeting_id: str) -> list[dict]:
        """Return action-item events for a meeting."""
        return self._db.events.get_action_items(meeting_id)

    # ------------------------------------------------------------------
    # Triplet store — insert and query
    # ------------------------------------------------------------------

    def insert_triplet(self, record: dict, embedding: list[float]) -> dict:
        """Insert a subject-predicate-object triplet with its embedding vector.

        Args:
            record: Triplet fields (see db/triplets.py for the full schema).
            embedding: 1536-dim float vector from the embedding model.

        Returns:
            The inserted row including generated id and created_at.
        """
        return self._db.triplets.insert(record, embedding)

    def search_triplets(
        self,
        query_embedding: list[float],
        threshold: float = 0.78,
        k: int = 10,
    ) -> list[dict]:
        """Semantic vector search over all triplets.

        Args:
            query_embedding: 1536-dim query vector.
            threshold: Minimum cosine similarity (0–1).
            k: Maximum results to return.

        Returns:
            Matching triplet rows augmented with a ``similarity`` field.
        """
        return self._db.triplets.search(query_embedding, threshold=threshold, k=k)

    def get_snapshot(self, meeting_id: str, sequence: int) -> list[dict]:
        """Return all triplets valid at a given sequence point in a meeting."""
        return self._db.triplets.get_snapshot(meeting_id, sequence)

    def get_entity_context(self, entity_id: str) -> list[dict]:
        """Return all triplets referencing an entity as subject or object."""
        return self._db.triplets.get_entity_context(entity_id)

    def get_open_tasks(self) -> list[dict]:
        """Return all open task-assignment triplets (assigned_to, no valid_until)."""
        return self._db.triplets.get_open_tasks()

    def close_prior_triplet(
        self,
        subject_id: str,
        predicate: str,
        new_object_id: str,
        at_sequence: int,
    ) -> None:
        """Invalidate superseded facts when a triplet is updated.

        Use for task reassignment, deadline change, or status update.
        """
        self._db.triplets.close_prior(subject_id, predicate, new_object_id, at_sequence)

    # ------------------------------------------------------------------
    # Triplet links
    # ------------------------------------------------------------------

    def create_triplet_links(self, triplet: dict) -> None:
        """Auto-link a newly inserted triplet to related existing triplets.

        Creates subject_match, object_match, and subject_object edges.
        Duplicate links are silently skipped.

        Args:
            triplet: Row returned by insert_triplet().
        """
        self._db.create_triplet_links(triplet)

    def insert_triplet_link(
        self,
        from_id: str,
        to_id: str,
        link_type: str,
        weight: float = 1.0,
    ) -> dict:
        """Manually insert a directed link between two triplets."""
        return self._db.triplet_links.create(from_id, to_id, link_type, weight)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def upload_transcript(
        self,
        meeting_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload a transcript file to the meeting-transcripts storage bucket.

        Returns the storage path.
        """
        return self._db.triplet_storage.upload_transcript(
            meeting_id, filename, content, content_type
        )

    def upload_audio(self, meeting_id: str, filename: str, content: bytes) -> str:
        """Upload an audio file to the meeting-audio storage bucket.

        Returns the storage path.
        """
        return self._db.triplet_storage.upload_audio(meeting_id, filename, content)


__all__ = ["MemoryGraph", "process_meeting_async"]
