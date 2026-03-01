"""Speaker diarization endpoints."""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, jsonify, request

from minute_bot.config import get_settings
from minute_bot.core import AudioBuffer, Diarizer
from minute_bot.pubsub import Publisher, Subscriber

logger = logging.getLogger(__name__)

bp = Blueprint("diarization", __name__, url_prefix="/diarization")

# Module-level state
_diarizer: Optional[Diarizer] = None
_subscriber: Optional[Subscriber] = None
_publisher: Optional[Publisher] = None
_is_processing = False
_audio_buffers: dict[str, AudioBuffer] = {}
_session_meeting_map: dict[str, str] = {}
_session_speakers: dict[str, dict[str, str]] = {}  # session -> {label: speaker_id}
_processing_stats = {
    "chunks_received": 0,
    "segments_processed": 0,
    "speakers_identified": 0,
    "errors": 0,
}


def _get_diarizer() -> Diarizer:
    """Get or create diarizer instance."""
    global _diarizer
    if _diarizer is None:
        _diarizer = Diarizer()
    return _diarizer


def _get_meeting_id(session_id: str) -> Optional[str]:
    """Get meeting ID for a session."""
    if session_id in _session_meeting_map:
        return _session_meeting_map[session_id]

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        meeting = db.meetings.get_by_session_id(session_id)
        if meeting:
            meeting_id = meeting.get("id")
            _session_meeting_map[session_id] = meeting_id
            return meeting_id
    except Exception as e:
        logger.error(f"Failed to get meeting ID: {e}")

    return None


def _get_or_create_speaker(
    session_id: str,
    speaker_label: str,
    meeting_id: str,
) -> Optional[str]:
    """Get or create speaker record and return speaker_id."""
    if session_id not in _session_speakers:
        _session_speakers[session_id] = {}

    speakers = _session_speakers[session_id]
    if speaker_label in speakers:
        return speakers[speaker_label]

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        speaker = db.speakers.create(
            meeting_id=meeting_id,
            speaker_label=speaker_label,
        )
        speaker_id = speaker.get("id")
        speakers[speaker_label] = speaker_id
        return speaker_id
    except Exception as e:
        logger.error(f"Failed to create speaker: {e}")
        return None


def _handle_audio_chunk(data: dict) -> None:
    """Process incoming audio chunk for diarization."""
    global _processing_stats

    try:
        session_id = data["session_id"]
        audio_data = data["audio_data"]

        if session_id not in _audio_buffers:
            _audio_buffers[session_id] = AudioBuffer()

        buffer = _audio_buffers[session_id]
        buffer.add_chunk(audio_data)
        _processing_stats["chunks_received"] += 1

        settings = get_settings()
        if buffer.get_duration() >= settings.diarization_buffer_duration:
            audio = buffer.get_audio()
            buffer.clear()

            diarizer = _get_diarizer()
            segments = diarizer.diarize(audio, session_id)

            meeting_id = _get_meeting_id(session_id)

            if _publisher:
                for segment in segments:
                    segment["timestamp"] = datetime.now(timezone.utc).isoformat()
                    _publisher.publish_diarization(segment)
                    _processing_stats["segments_processed"] += 1

                    if meeting_id:
                        speaker_id = _get_or_create_speaker(
                            session_id, segment["speaker_id"], meeting_id
                        )
                        if speaker_id:
                            _update_speaker_time(
                                speaker_id, segment["end_time"] - segment["start_time"]
                            )

            logger.debug(
                f"Diarized {len(segments)} segments for session {session_id}"
            )

    except Exception as e:
        _processing_stats["errors"] += 1
        logger.error(f"Error processing chunk for diarization: {e}")


def _update_speaker_time(speaker_id: str, duration: float) -> None:
    """Update speaker's total speaking time."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        db.speakers.update_speaking_time(speaker_id, duration)
    except Exception as e:
        logger.error(f"Failed to update speaker time: {e}")


@bp.route("/start", methods=["POST"])
def start_processing():
    """Start diarization processing."""
    global _subscriber, _publisher, _is_processing

    if _is_processing:
        return jsonify({"status": "already_running"}), 409

    _publisher = Publisher()
    _subscriber = Subscriber()
    _subscriber.subscribe_audio(_handle_audio_chunk)
    _subscriber.start()
    _is_processing = True

    # Preload models
    _get_diarizer()

    logger.info("Diarization processing started")
    return jsonify({"status": "started"})


@bp.route("/stop", methods=["POST"])
def stop_processing():
    """Stop diarization processing."""
    global _subscriber, _is_processing

    if not _is_processing:
        return jsonify({"status": "not_running"}), 409

    if _subscriber:
        _subscriber.stop()

    _is_processing = False
    logger.info("Diarization processing stopped")
    return jsonify({"status": "stopped"})


@bp.route("/status", methods=["GET"])
def get_status():
    """Get processing status."""
    settings = get_settings()
    return jsonify(
        {
            "is_processing": _is_processing,
            "buffer_duration": settings.diarization_buffer_duration,
            "min_speakers": settings.min_speakers,
            "max_speakers": settings.max_speakers,
            "stats": _processing_stats,
            "active_sessions": list(_audio_buffers.keys()),
        }
    )


@bp.route("/speakers/<meeting_id>", methods=["GET"])
def get_speakers(meeting_id: str):
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


@bp.route("/speakers/<speaker_id>/name", methods=["PUT"])
def update_speaker_name(speaker_id: str):
    """Update speaker name."""
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
