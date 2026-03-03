"""Post-meeting graph processing — triggered by the user via the UI.

This module is the second post-processing stage, run after speaker attribution
completes.  It is intentionally NOT automatic: the UI shows a "Process
Transcript" button which calls POST /meetings/<id>/process, which calls
run_graph_processing_async().

Pipeline
--------
1. LLM transcript cleanup
       Raw attributed transcripts → clean sentences → processed_transcripts table
       graph_processing_status = "processing_transcripts"

2. Knowledge-graph extraction
       processed_transcripts → LLM agent → events + entities + relationships
       graph_processing_status = "processing_graph"

3. Completion
       graph_processing_status = "completed"

Progress tracking
-----------------
graph_processing_status column on the meetings table uses these values:
    null / "pending"              → not yet started
    "processing_transcripts"      → step 1 in progress
    "processing_graph"            → step 2 in progress
    "completed"                   → done; graph is ready
    "failed"                      → unrecoverable error
"""

import logging
import threading

logger = logging.getLogger(__name__)


def generate_knowledge_graph(meeting_id: str, db) -> None:
    """Extract events, entities, and relationships from processed transcripts.

    Reads the processed_transcripts for the meeting (written by step 1),
    runs the graph_generation LLM agent, and persists the results.
    """
    from minute_bot.agents import graph_generation as graph_agent

    transcripts = db.processed_transcripts.get_by_meeting(meeting_id)
    if not transcripts:
        logger.warning("graph_processing: no processed transcripts for meeting %s", meeting_id)
        return

    logger.info(
        "graph_processing: extracting graph from %d sentences for meeting %s",
        len(transcripts), meeting_id,
    )

    result = graph_agent.run(transcripts)

    # ── Entities ──────────────────────────────────────────────────────────────
    entity_name_to_id: dict[str, str] = {}
    for e in result.get("entities", []):
        try:
            row = db.entities.get_or_create(
                meeting_id, e["entity_type"], e["entity_name"]
            )
            entity_name_to_id[e["entity_name"]] = row["id"]
        except Exception as exc:
            logger.error("graph_processing: failed to insert entity %r: %s", e, exc)

    logger.info("graph_processing: persisted %d entities", len(entity_name_to_id))

    # ── Events ────────────────────────────────────────────────────────────────
    events_inserted = 0
    for ev in result.get("events", []):
        try:
            db.events.create(
                meeting_id=meeting_id,
                event_type=ev["event_type"],
                description=ev["description"],
                timestamp=float(ev.get("timestamp") or 0.0),
            )
            events_inserted += 1
        except Exception as exc:
            logger.error("graph_processing: failed to insert event %r: %s", ev, exc)

    logger.info("graph_processing: persisted %d events", events_inserted)

    # ── Relationships ─────────────────────────────────────────────────────────
    rels_inserted = 0
    for rel in result.get("relationships", []):
        src_id = entity_name_to_id.get(rel["source_entity"])
        tgt_id = entity_name_to_id.get(rel["target_entity"])
        if not src_id or not tgt_id:
            logger.debug(
                "graph_processing: skipping relationship %r — entity not found",
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
            rels_inserted += 1
        except Exception as exc:
            logger.error("graph_processing: failed to insert relationship %r: %s", rel, exc)

    logger.info("graph_processing: persisted %d relationships", rels_inserted)


def run_graph_processing(meeting_id: str) -> None:
    """Run both post-processing steps for a completed meeting.

    Called from a daemon thread via run_graph_processing_async().

    Progress is written to meeting.graph_processing_status at each step so the
    frontend can poll and show a live indicator.
    """
    from minute_bot.api.transcript_processing import process_meeting_transcripts
    from minute_bot.db import MinuteBotDB

    db = MinuteBotDB()

    # ── Step 1: LLM transcript cleanup ───────────────────────────────────────
    try:
        db.meetings.update_graph_processing_status(meeting_id, "processing_transcripts")
    except Exception as e:
        logger.error("graph_processing: failed to set status for %s: %s", meeting_id, e)
        return

    try:
        logger.info("graph_processing: step 1 — transcript cleanup for meeting %s", meeting_id)
        process_meeting_transcripts(meeting_id)
    except Exception as e:
        logger.error("graph_processing: transcript cleanup failed for %s: %s", meeting_id, e)
        try:
            db.meetings.update_graph_processing_status(meeting_id, "failed")
        except Exception:
            pass
        return

    # ── Step 2: knowledge-graph extraction ───────────────────────────────────
    try:
        db.meetings.update_graph_processing_status(meeting_id, "processing_graph")
    except Exception as e:
        logger.error("graph_processing: failed to advance status for %s: %s", meeting_id, e)

    try:
        logger.info("graph_processing: step 2 — graph extraction for meeting %s", meeting_id)
        generate_knowledge_graph(meeting_id, db)
    except Exception as e:
        logger.error("graph_processing: graph extraction failed for %s: %s", meeting_id, e)
        try:
            db.meetings.update_graph_processing_status(meeting_id, "failed")
        except Exception:
            pass
        return

    # ── Done ──────────────────────────────────────────────────────────────────
    try:
        db.meetings.update_graph_processing_status(meeting_id, "completed")
        logger.info("graph_processing: completed for meeting %s", meeting_id)
    except Exception as e:
        logger.error("graph_processing: failed to mark completed for %s: %s", meeting_id, e)


def run_graph_processing_async(meeting_id: str) -> None:
    """Spawn a daemon thread to run graph processing without blocking the HTTP response."""
    thread = threading.Thread(
        target=run_graph_processing,
        args=(meeting_id,),
        daemon=True,
        name=f"graph-processing-{meeting_id[:8]}",
    )
    thread.start()
