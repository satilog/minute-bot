"""Transcription endpoints."""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, jsonify, request

from minute_bot.audio import decode_audio_base64
from minute_bot.config import get_settings
from minute_bot.core import AudioBuffer, Transcriber, get_available_models
from minute_bot.pubsub import Publisher, Subscriber

logger = logging.getLogger(__name__)

bp = Blueprint("transcription", __name__, url_prefix="/transcription")

# Module-level state
_transcriber: Optional[Transcriber] = None
_subscriber: Optional[Subscriber] = None
_publisher: Optional[Publisher] = None
_is_processing = False
_audio_buffers: dict[str, AudioBuffer] = {}
_session_meeting_map: dict[str, str] = {}
_processing_stats = {
    "chunks_received": 0,
    "segments_transcribed": 0,
    "segments_persisted": 0,
    "errors": 0,
}


def _get_transcriber() -> Transcriber:
    """Get or create transcriber instance."""
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber


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


def _handle_audio_chunk(data: dict) -> None:
    """Process incoming audio chunk."""
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
        if buffer.get_duration() >= settings.transcription_buffer_duration:
            audio = buffer.get_audio()
            buffer.clear()

            transcriber = _get_transcriber()
            segments = transcriber.transcribe(audio, session_id)

            meeting_id = _get_meeting_id(session_id)

            if _publisher:
                for segment in segments:
                    segment["timestamp"] = datetime.now(timezone.utc).isoformat()
                    _publisher.publish_transcript(segment)
                    _processing_stats["segments_transcribed"] += 1

                    if meeting_id:
                        _persist_transcript(segment, meeting_id)

            logger.debug(
                f"Transcribed {len(segments)} segments for session {session_id}"
            )

    except Exception as e:
        _processing_stats["errors"] += 1
        logger.error(f"Error processing chunk: {e}")


def _persist_transcript(segment: dict, meeting_id: str) -> None:
    """Persist transcript segment to database."""
    global _processing_stats

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        db.transcripts.create(
            meeting_id=meeting_id,
            text=segment["text"],
            start_time=segment["start_time"],
            end_time=segment["end_time"],
            confidence=segment.get("confidence", 1.0),
            speaker_id=segment.get("speaker_id"),
        )
        _processing_stats["segments_persisted"] += 1
    except Exception as e:
        logger.error(f"Failed to persist transcript: {e}")


@bp.route("/start", methods=["POST"])
def start_processing():
    """Start transcription processing."""
    global _subscriber, _publisher, _is_processing

    if _is_processing:
        return jsonify({"status": "already_running"}), 409

    _publisher = Publisher()
    _subscriber = Subscriber()
    _subscriber.subscribe_audio(_handle_audio_chunk)
    _subscriber.start()
    _is_processing = True

    # Preload model
    _get_transcriber()

    logger.info("Transcription processing started")
    return jsonify({"status": "started"})


@bp.route("/stop", methods=["POST"])
def stop_processing():
    """Stop transcription processing."""
    global _subscriber, _is_processing

    if not _is_processing:
        return jsonify({"status": "not_running"}), 409

    if _subscriber:
        _subscriber.stop()

    _is_processing = False
    logger.info("Transcription processing stopped")
    return jsonify({"status": "stopped"})


@bp.route("/status", methods=["GET"])
def get_status():
    """Get processing status."""
    settings = get_settings()
    return jsonify(
        {
            "is_processing": _is_processing,
            "model": settings.whisper_model,
            "buffer_duration": settings.transcription_buffer_duration,
            "language": settings.language,
            "stats": _processing_stats,
            "active_sessions": list(_audio_buffers.keys()),
        }
    )


@bp.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    """Direct transcription endpoint for testing."""
    data = request.get_json()

    if not data or "audio_data" not in data:
        return jsonify({"error": "Missing audio_data"}), 400

    try:
        audio = decode_audio_base64(data["audio_data"])
        session_id = data.get("session_id", str(uuid.uuid4()))

        transcriber = _get_transcriber()
        segments = transcriber.transcribe(audio, session_id)

        return jsonify(
            {
                "session_id": session_id,
                "segments": segments,
                "count": len(segments),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/transcripts/<meeting_id>", methods=["GET"])
def get_transcripts(meeting_id: str):
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


@bp.route("/models", methods=["GET"])
def list_models():
    """List available Whisper models."""
    settings = get_settings()
    return jsonify(
        {
            "available": get_available_models(),
            "current": settings.whisper_model,
        }
    )
