"""Meeting CRUD endpoints."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("meetings", __name__, url_prefix="/meetings")


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
    """Get meeting details with all related data."""
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
        return jsonify(
            {
                "meeting_id": meeting_id,
                "transcripts": transcripts,
                "count": len(transcripts),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/speakers", methods=["GET"])
def get_meeting_speakers(meeting_id: str):
    """Get speakers for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        speakers = db.speakers.get_by_meeting(meeting_id)
        return jsonify(
            {
                "meeting_id": meeting_id,
                "speakers": speakers,
                "count": len(speakers),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/events", methods=["GET"])
def get_meeting_events(meeting_id: str):
    """Get events for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        event_type = request.args.get("type")
        events = db.events.get_by_meeting(meeting_id, event_type=event_type)
        return jsonify(
            {
                "meeting_id": meeting_id,
                "events": events,
                "count": len(events),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/action-items", methods=["GET"])
def get_action_items(meeting_id: str):
    """Get action items for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        items = db.events.get_action_items(meeting_id)
        return jsonify(
            {
                "meeting_id": meeting_id,
                "action_items": items,
                "count": len(items),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/entities", methods=["GET"])
def get_meeting_entities(meeting_id: str):
    """Get entities for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        entity_type = request.args.get("type")
        entities = db.entities.get_by_meeting(meeting_id, entity_type=entity_type)
        return jsonify(
            {
                "meeting_id": meeting_id,
                "entities": entities,
                "count": len(entities),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<meeting_id>/audio", methods=["GET"])
def get_meeting_audio(meeting_id: str):
    """Get audio files for a meeting."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        files = db.audio_files.get_by_meeting(meeting_id)

        # Generate signed URLs for audio files
        for f in files:
            if f.get("file_path"):
                f["url"] = db.audio_files.get_audio_url(f["file_path"])

        return jsonify(
            {
                "meeting_id": meeting_id,
                "audio_files": files,
                "count": len(files),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
