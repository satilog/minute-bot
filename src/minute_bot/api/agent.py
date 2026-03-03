"""Agent query endpoint — natural language Q&A over meeting data."""

import logging

from apiflask import APIBlueprint
from flask import jsonify, request

logger = logging.getLogger(__name__)

bp = APIBlueprint("agent", __name__, url_prefix="/agent", tag="agent")


@bp.route("/query", methods=["POST"])
def query_agent():
    """
    Answer a natural language question about a meeting.

    Body: {query: str, session_id: str, meeting_id: str}
    Response: {answer: str, sources: list[str], node?: {label, type, data}}
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query")
    session_id = data.get("session_id")
    meeting_id = data.get("meeting_id")

    if not query or not session_id or not meeting_id:
        return jsonify({"error": "query, session_id, and meeting_id are required"}), 400

    people_types = {
        "person",
        "speaker",
        "assignee",
        "owner",
        "reviewer",
        "stakeholder",
        "organization",
    }

    entities = []
    events = []
    transcripts = []

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()

        try:
            entities = db.entities.get_by_meeting(meeting_id) or []
        except Exception:
            logger.warning("Failed to fetch entities for meeting %s", meeting_id)

        try:
            events = db.events.get_by_meeting(meeting_id) or []
        except Exception:
            logger.warning("Failed to fetch events for meeting %s", meeting_id)

        try:
            transcripts = db.transcripts.get_by_meeting(meeting_id) or []
        except Exception:
            logger.warning("Failed to fetch transcripts for meeting %s", meeting_id)

    except Exception:
        logger.exception("Failed to initialise DB for agent query")

    query_lower = query.lower()

    matched_entities = [
        e for e in entities if query_lower in e.get("entity_name", "").lower()
    ]
    matched_events = [
        e for e in events if query_lower in e.get("description", "").lower()
    ]
    matched_transcripts = [
        t for t in transcripts if query_lower in t.get("text", "").lower()
    ]

    answer_parts = []
    sources = []
    node = None

    if matched_entities:
        names = [e.get("entity_name", "") for e in matched_entities]
        answer_parts.append(
            f"Found {len(matched_entities)} related entities: {', '.join(names)}"
        )
        sources.extend(names)

        best = matched_entities[0]
        entity_type = (best.get("entity_type") or "").lower()
        node = {
            "label": best.get("entity_name"),
            "type": "entity" if entity_type in people_types else "artifact",
            "data": {
                "entity_type": entity_type,
                "entity_name": best.get("entity_name"),
            },
        }

    if matched_events:
        descriptions = [e.get("description", "") for e in matched_events]
        answer_parts.append(f"Related events: {'; '.join(descriptions)}")
        sources.extend(descriptions)

    if matched_transcripts:
        answer_parts.append("Relevant transcript excerpts found.")

    if not answer_parts:
        answer = f"No information found about '{query}' in this meeting."
    else:
        answer = " ".join(answer_parts)

    return jsonify({"answer": answer, "sources": sources, "node": node})
