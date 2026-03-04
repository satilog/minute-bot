"""Memory-graph pipeline — triggered by the user via the UI.

This module is the second post-processing stage, run after speaker attribution
completes.  It is intentionally NOT automatic: the UI shows a "Process
Transcript" button which calls POST /meetings/<id>/process, which calls
process_meeting_async().

Pipeline
--------
1. LLM transcript cleanup
       Raw attributed transcripts → clean sentences → processed_transcripts table
       graph_processing_status = "processing_transcripts"

2. Knowledge-graph extraction (chunked)
       processed_transcripts → split into CHUNK_SIZE-sentence windows →
       LLM agent per chunk → events + entities + relationships
       graph_processing_status = "processing_graph"

3. Completion
       graph_processing_status = "completed"

Progress values
---------------
    null / "pending"              → not yet started
    "processing_transcripts"      → step 1 in progress
    "processing_graph"            → step 2 in progress
    "completed"                   → done; graph is ready
    "failed"                      → unrecoverable error

Chunking strategy
-----------------
The full list of processed transcripts is split into windows of at most
CHUNK_SIZE sentences.  Each chunk is sent to the LLM independently so that
context fits within the model's window and extraction quality stays high.

Entities accumulate in a shared name→id map across all chunks so that
relationships extracted in later chunks can still resolve entities that were
first mentioned in earlier ones.  DB-level deduplication (get_or_create) means
the same entity name is never inserted twice even if the LLM names it in
multiple chunks.
"""

import logging
import threading

from minute_bot.memory_graph import extraction

logger = logging.getLogger(__name__)

# Maximum number of sentences sent to the LLM in a single extraction call.
# Keeping this well below typical context limits ensures consistent output
# quality for both short and long meetings.
_CHUNK_SIZE = 50


def _extract_and_persist(meeting_id: str, db) -> None:
    """Run the graph extraction agent in chunks and persist the results.

    Splits processed_transcripts into windows of _CHUNK_SIZE sentences, calls
    the LLM extraction agent on each window, and accumulates entities, events,
    and relationships across all chunks before writing to the database.
    """
    transcripts = db.processed_transcripts.get_by_meeting(meeting_id)
    if not transcripts:
        logger.warning(
            "memory_graph.processing: no processed transcripts for meeting %s",
            meeting_id,
        )
        return

    chunks = [
        transcripts[i : i + _CHUNK_SIZE]
        for i in range(0, len(transcripts), _CHUNK_SIZE)
    ]
    total_chunks = len(chunks)

    logger.info(
        "memory_graph.processing: extracting graph from %d sentences "
        "(%d chunk(s) of up to %d) for meeting %s",
        len(transcripts), total_chunks, _CHUNK_SIZE, meeting_id,
    )

    # entity_name_to_id grows across all chunks so later chunks can resolve
    # relationships that reference entities introduced in earlier chunks.
    entity_name_to_id: dict[str, str] = {}
    total_events = 0
    total_rels = 0

    for chunk_idx, chunk in enumerate(chunks):
        logger.info(
            "memory_graph.processing: chunk %d/%d (%d sentences)",
            chunk_idx + 1, total_chunks, len(chunk),
        )

        result = extraction.run(chunk)

        # Entities
        for e in result.get("entities", []):
            try:
                row = db.entities.get_or_create(
                    meeting_id, e["entity_type"], e["entity_name"]
                )
                entity_name_to_id[e["entity_name"]] = row["id"]
            except Exception as exc:
                logger.error(
                    "memory_graph.processing: failed to insert entity %r: %s", e, exc
                )

        # Events
        for ev in result.get("events", []):
            try:
                db.events.create(
                    meeting_id=meeting_id,
                    event_type=ev["event_type"],
                    description=ev["description"],
                    timestamp=float(ev.get("timestamp") or 0.0),
                )
                total_events += 1
            except Exception as exc:
                logger.error(
                    "memory_graph.processing: failed to insert event %r: %s", ev, exc
                )

        # Relationships — resolve against cumulative entity map
        for rel in result.get("relationships", []):
            src_id = entity_name_to_id.get(rel["source_entity"])
            tgt_id = entity_name_to_id.get(rel["target_entity"])
            if not src_id or not tgt_id:
                logger.debug(
                    "memory_graph.processing: skipping relationship %r — entity not found",
                    rel,
                )
                continue
            try:
                db.relationships.create(
                    meeting_id=meeting_id,
                    source_entity_id=src_id,
                    target_entity_id=tgt_id,
                    relationship_type=rel["relationship_type"],
                )
                total_rels += 1
            except Exception as exc:
                logger.error(
                    "memory_graph.processing: failed to insert relationship %r: %s",
                    rel, exc,
                )

        logger.info(
            "memory_graph.processing: after chunk %d/%d — "
            "entities=%d events=%d relationships=%d",
            chunk_idx + 1, total_chunks,
            len(entity_name_to_id), total_events, total_rels,
        )

    logger.info(
        "memory_graph.processing: extraction complete — "
        "entities=%d events=%d relationships=%d",
        len(entity_name_to_id), total_events, total_rels,
    )


def run(meeting_id: str) -> None:
    """Run both post-processing steps for a completed meeting.

    Called from a daemon thread via process_meeting_async().

    Progress is written to meeting.graph_processing_status at each step so the
    frontend can poll and show a live indicator.
    """
    from minute_bot.api.transcript_processing import process_meeting_transcripts
    from minute_bot.db import MinuteBotDB

    db = MinuteBotDB()

    # Step 1: LLM transcript cleanup
    try:
        db.meetings.update_graph_processing_status(meeting_id, "processing_transcripts")
    except Exception as e:
        logger.error(
            "memory_graph.processing: failed to set status for %s: %s", meeting_id, e
        )
        return

    try:
        logger.info(
            "memory_graph.processing: step 1 — transcript cleanup for meeting %s",
            meeting_id,
        )
        process_meeting_transcripts(meeting_id)
    except Exception as e:
        logger.error(
            "memory_graph.processing: transcript cleanup failed for %s: %s",
            meeting_id, e,
        )
        try:
            db.meetings.update_graph_processing_status(meeting_id, "failed")
        except Exception:
            pass
        return

    # Step 2: Knowledge-graph extraction
    try:
        db.meetings.update_graph_processing_status(meeting_id, "processing_graph")
    except Exception as e:
        logger.error(
            "memory_graph.processing: failed to advance status for %s: %s",
            meeting_id, e,
        )

    try:
        logger.info(
            "memory_graph.processing: step 2 — graph extraction for meeting %s",
            meeting_id,
        )
        _extract_and_persist(meeting_id, db)
    except Exception as e:
        logger.error(
            "memory_graph.processing: graph extraction failed for %s: %s",
            meeting_id, e,
        )
        try:
            db.meetings.update_graph_processing_status(meeting_id, "failed")
        except Exception:
            pass
        return

    # Done
    try:
        db.meetings.update_graph_processing_status(meeting_id, "completed")
        logger.info("memory_graph.processing: completed for meeting %s", meeting_id)
    except Exception as e:
        logger.error(
            "memory_graph.processing: failed to mark completed for %s: %s",
            meeting_id, e,
        )


def process_meeting_async(meeting_id: str) -> None:
    """Spawn a daemon thread to run graph processing without blocking the HTTP response."""
    thread = threading.Thread(
        target=run,
        args=(meeting_id,),
        daemon=True,
        name=f"memory-graph-{meeting_id[:8]}",
    )
    thread.start()
