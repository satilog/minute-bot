"""Meeting endpoints — primary workflow API."""

import logging
import uuid
from datetime import datetime, timezone

from apiflask import APIBlueprint
from flask import jsonify, request

logger = logging.getLogger(__name__)

bp = APIBlueprint("meetings", __name__, url_prefix="/meetings", tag="meetings")

# Active sessions: session_id → meeting_id
_active_sessions: dict[str, str] = {}


@bp.route("/start", methods=["POST"])
def start_meeting():
    """
    Create a new meeting record and return session credentials.
    The client uses session_id to tag streamed audio chunks.
    """
    data = request.get_json() or {}
    title = data.get("title")
    session_id = str(uuid.uuid4())

    meeting_id = None
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        meeting = db.meetings.create(session_id, title=title)
        meeting_id = meeting.get("id")
        _active_sessions[session_id] = meeting_id
        logger.info(f"Meeting started: {meeting_id} (session={session_id})")
    except Exception as e:
        logger.warning(f"Failed to create meeting record: {e}")

    return jsonify({
        "status": "started",
        "session_id": session_id,
        "meeting_id": meeting_id,
    })


@bp.route("/stream", methods=["POST"])
def stream_chunk():
    """
    Receive an audio chunk from the client and forward it into the pipeline.
    Expected body: {session_id, chunk_index, sample_rate, audio_data (base64)}
    """
    from minute_bot.api.streaming import _publish_chunk

    data = request.get_json()
    if not data or "audio_data" not in data or "session_id" not in data:
        return jsonify({"error": "Missing session_id or audio_data"}), 400

    chunk = {
        "session_id": data["session_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chunk_index": data.get("chunk_index", 0),
        "sample_rate": data.get("sample_rate", 16000),
        "channels": 1,
        "format": "int16",
        "audio_data": data["audio_data"],
    }

    _publish_chunk(chunk)
    return jsonify({"status": "ok"}), 200


@bp.route("/stop", methods=["POST"])
def stop_meeting():
    """
    Stop a meeting. Client sends {session_id, meeting_id} in the body.
    Server saves accumulated audio and marks the meeting complete.
    """
    from minute_bot.api.streaming import _save_audio_to_supabase
    from minute_bot.config import get_settings

    data = request.get_json() or {}
    session_id = data.get("session_id")
    meeting_id = data.get("meeting_id")

    if not session_id or not meeting_id:
        return jsonify({"error": "Missing session_id or meeting_id"}), 400

    _active_sessions.pop(session_id, None)
    logger.info(f"Meeting stopped: {meeting_id} (session={session_id})")

    settings = get_settings()
    if settings.save_audio_to_storage:
        _save_audio_to_supabase(session_id, meeting_id)

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        db.meetings.update_status(meeting_id, "completed")
    except Exception as e:
        logger.error(f"Failed to update meeting status: {e}")

    return jsonify({
        "status": "stopped",
        "session_id": session_id,
        "meeting_id": meeting_id,
    })


@bp.route("/status", methods=["GET"])
def recording_status():
    """Return currently active recording sessions."""
    return jsonify({
        "active_sessions": [
            {"session_id": sid, "meeting_id": mid}
            for sid, mid in _active_sessions.items()
        ],
        "count": len(_active_sessions),
    })


@bp.route("", methods=["GET"])
def list_meetings():
    """List recent meetings."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        limit = request.args.get("limit", 10, type=int)
        meetings = db.meetings.list_recent(limit=limit)
        return jsonify({"meetings": meetings, "count": len(meetings)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>", methods=["GET"])
def get_meeting(meeting_id: str):
    """Get full meeting summary with all related data."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        summary = db.get_meeting_summary(meeting_id)
        if not summary:
            return jsonify({"error": "Meeting not found"}), 404
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/transcripts", methods=["GET"])
def get_meeting_transcripts(meeting_id: str):
    """Get transcripts for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        transcripts = db.transcripts.get_by_meeting(meeting_id)
        return jsonify({
            "meeting_id": meeting_id,
            "transcripts": transcripts,
            "count": len(transcripts),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/speakers", methods=["GET"])
def get_meeting_speakers(meeting_id: str):
    """Get speakers for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        speakers = db.speakers.get_by_meeting(meeting_id)
        return jsonify({
            "meeting_id": meeting_id,
            "speakers": speakers,
            "count": len(speakers),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/speakers/<speaker_id>/name", methods=["PUT"])
def update_speaker_name(meeting_id: str, speaker_id: str):
    """Update a speaker's display name."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing name"}), 400

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        speaker = db.speakers.update_name(speaker_id, data["name"])
        return jsonify({"speaker": speaker})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/events", methods=["GET"])
def get_meeting_events(meeting_id: str):
    """Get events for a meeting. Optional ?type= filter."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        event_type = request.args.get("type")
        events = db.events.get_by_meeting(meeting_id, event_type=event_type)
        return jsonify({
            "meeting_id": meeting_id,
            "events": events,
            "count": len(events),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/action-items", methods=["GET"])
def get_action_items(meeting_id: str):
    """Get action items for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        items = db.events.get_action_items(meeting_id)
        return jsonify({
            "meeting_id": meeting_id,
            "action_items": items,
            "count": len(items),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/entities", methods=["GET"])
def get_meeting_entities(meeting_id: str):
    """Get entities for a meeting. Optional ?type= filter."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        entity_type = request.args.get("type")
        entities = db.entities.get_by_meeting(meeting_id, entity_type=entity_type)
        return jsonify({
            "meeting_id": meeting_id,
            "entities": entities,
            "count": len(entities),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/audio", methods=["GET"])
def get_meeting_audio(meeting_id: str):
    """Get audio files for a meeting with signed download URLs."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        files = db.audio_files.get_by_meeting(meeting_id)
        for f in files:
            if f.get("file_path"):
                f["url"] = db.audio_files.get_audio_url(f["file_path"])
        return jsonify({
            "meeting_id": meeting_id,
            "audio_files": files,
            "count": len(files),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
