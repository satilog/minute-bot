"""Transcription processing — auto-started at server boot."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from apiflask import APIBlueprint
from flask import jsonify, request

from minute_bot.audio import decode_audio_base64
from minute_bot.config import get_settings
from minute_bot.core import AudioBuffer, get_available_models
from minute_bot.pubsub import Subscriber
from minute_bot.services import registry

logger = logging.getLogger(__name__)

bp = APIBlueprint("transcription", __name__, url_prefix="/transcription", tag="transcription")

# Internal state
_subscriber: Optional[Subscriber] = None
_is_processing = False
_audio_buffers: dict[str, AudioBuffer] = {}
_session_meeting_map: dict[str, str] = {}
_processing_stats = {
    "chunks_received": 0,
    "segments_transcribed": 0,
    "segments_persisted": 0,
    "errors": 0,
}


def _init_processing() -> None:
    """Start the transcription subscriber. Called automatically at server startup."""
    global _subscriber, _is_processing

    _subscriber = Subscriber()
    _subscriber.subscribe_audio(_handle_audio_chunk)
    _subscriber.start()
    _is_processing = True
    logger.info("[startup:transcription] Subscriber started")


def _get_meeting_id(session_id: str) -> Optional[str]:
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
            if registry.transcriber is None:
                logger.warning("[transcription] Whisper not yet ready, skipping chunk")
                return

            audio = buffer.get_audio()
            buffer.clear()

            segments = registry.transcriber.transcribe(audio, session_id)
            meeting_id = _get_meeting_id(session_id)

            if registry.publisher:
                for segment in segments:
                    segment["timestamp"] = datetime.now(timezone.utc).isoformat()
                    registry.publisher.publish_transcript(segment)
                    _processing_stats["segments_transcribed"] += 1

                    if meeting_id:
                        _persist_transcript(segment, meeting_id)

            logger.debug(f"Transcribed {len(segments)} segments for session {session_id}")

    except Exception as e:
        _processing_stats["errors"] += 1
        logger.error(f"Error processing chunk: {e}")


def _persist_transcript(segment: dict, meeting_id: str) -> None:
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


@bp.route("/status", methods=["GET"])
def get_status():
    """Diagnostic: transcription pipeline state."""
    settings = get_settings()
    return jsonify({
        "is_processing": _is_processing,
        "model": settings.whisper_model,
        "model_status": registry.get_status().get("whisper"),
        "buffer_duration": settings.transcription_buffer_duration,
        "language": settings.language,
        "stats": _processing_stats,
        "active_sessions": list(_audio_buffers.keys()),
    })


@bp.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    """Direct transcription for testing — POST {audio_data: <base64>}."""
    data = request.get_json()

    if not data or "audio_data" not in data:
        return jsonify({"error": "Missing audio_data"}), 400

    if registry.transcriber is None:
        return jsonify({
            "error": "Whisper model not yet loaded",
            "model_status": registry.get_status().get("whisper"),
        }), 503

    try:
        audio = decode_audio_base64(data["audio_data"])
        session_id = data.get("session_id", str(uuid.uuid4()))
        segments = registry.transcriber.transcribe(audio, session_id)
        return jsonify({"session_id": session_id, "segments": segments, "count": len(segments)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/models", methods=["GET"])
def list_models():
    """List available Whisper models."""
    settings = get_settings()
    return jsonify({"available": get_available_models(), "current": settings.whisper_model})
