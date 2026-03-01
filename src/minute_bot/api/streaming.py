"""Audio streaming control endpoints."""

import io
import logging
import threading
import wave
from typing import Optional

import numpy as np
from flask import Blueprint, current_app, jsonify, request

from minute_bot.audio import decode_audio_base64
from minute_bot.config import get_settings
from minute_bot.core import AudioCapture, get_audio_devices
from minute_bot.pubsub import Publisher

logger = logging.getLogger(__name__)

bp = Blueprint("streaming", __name__, url_prefix="/streaming")

# Module-level state
_audio_capture: Optional[AudioCapture] = None
_publisher: Optional[Publisher] = None
_current_meeting_id: Optional[str] = None
_audio_accumulator: list = []
_accumulator_lock = threading.Lock()


def _publish_chunk(chunk: dict) -> None:
    """Callback for audio capture to publish chunks."""
    global _publisher, _audio_accumulator

    if _publisher:
        _publisher.publish_audio_chunk(chunk)

    settings = get_settings()
    if settings.save_audio_to_storage:
        with _accumulator_lock:
            _audio_accumulator.append(chunk["audio_data"])


def _init_capture() -> None:
    """Initialize audio capture if needed."""
    global _audio_capture, _publisher

    if _audio_capture is None:
        _audio_capture = AudioCapture(on_chunk=_publish_chunk)

    if _publisher is None:
        _publisher = Publisher()


@bp.route("/start", methods=["POST"])
def start_capture():
    """Start audio capture and streaming."""
    global _audio_capture, _current_meeting_id, _audio_accumulator

    _init_capture()

    if _audio_capture.is_running:
        return (
            jsonify(
                {
                    "status": "already_running",
                    "session_id": _audio_capture.session_id,
                    "meeting_id": _current_meeting_id,
                }
            ),
            409,
        )

    try:
        data = request.get_json() or {}
        title = data.get("title")

        session_id = _audio_capture.start()

        with _accumulator_lock:
            _audio_accumulator.clear()

        # Create meeting record
        try:
            from minute_bot.db import MinuteBotDB

            db = MinuteBotDB()
            meeting = db.meetings.create(session_id, title=title)
            _current_meeting_id = meeting.get("id")
            logger.info(f"Created meeting record: {_current_meeting_id}")
        except Exception as e:
            logger.warning(f"Failed to create meeting record: {e}")
            _current_meeting_id = None

        settings = get_settings()
        return jsonify(
            {
                "status": "started",
                "session_id": session_id,
                "meeting_id": _current_meeting_id,
                "config": {
                    "sample_rate": _audio_capture.SAMPLE_RATE,
                    "channels": _audio_capture.CHANNELS,
                    "chunk_size": _audio_capture.CHUNK_SIZE,
                    "redis_channel": settings.audio_channel,
                },
            }
        )

    except Exception as e:
        logger.error(f"Failed to start capture: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/stop", methods=["POST"])
def stop_capture():
    """Stop audio capture and streaming."""
    global _audio_capture, _current_meeting_id

    if _audio_capture is None or not _audio_capture.is_running:
        return jsonify({"status": "not_running"}), 409

    session_id = _audio_capture.session_id
    meeting_id = _current_meeting_id

    _audio_capture.stop()
    logger.info(f"Stopped audio capture session: {session_id}")

    # Save audio to Supabase Storage
    settings = get_settings()
    if settings.save_audio_to_storage and meeting_id:
        _save_audio_to_supabase(session_id, meeting_id)

    # Update meeting status
    if meeting_id:
        try:
            from minute_bot.db import MinuteBotDB

            db = MinuteBotDB()
            db.meetings.update_status(meeting_id, "completed")
            logger.info(f"Updated meeting status to completed: {meeting_id}")
        except Exception as e:
            logger.error(f"Failed to update meeting status: {e}")

    _current_meeting_id = None

    return jsonify(
        {
            "status": "stopped",
            "session_id": session_id,
            "meeting_id": meeting_id,
        }
    )


@bp.route("/status", methods=["GET"])
def get_status():
    """Get current capture status."""
    global _audio_capture, _current_meeting_id

    if _audio_capture is None:
        return jsonify(
            {
                "is_running": False,
                "session_id": None,
                "meeting_id": None,
            }
        )

    status = _audio_capture.get_status()
    status["meeting_id"] = _current_meeting_id

    with _accumulator_lock:
        status["accumulated_chunks"] = len(_audio_accumulator)

    return jsonify(status)


@bp.route("/devices", methods=["GET"])
def list_devices():
    """List available audio input devices."""
    try:
        devices = get_audio_devices()
        return jsonify({"devices": devices, "count": len(devices)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _save_audio_to_supabase(session_id: str, meeting_id: str) -> None:
    """Save accumulated audio to Supabase Storage."""
    global _audio_accumulator

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
    except Exception:
        return

    with _accumulator_lock:
        chunks = _audio_accumulator.copy()
        _audio_accumulator.clear()

    if not chunks:
        return

    try:
        all_audio = [decode_audio_base64(chunk) for chunk in chunks]
        full_audio = np.concatenate(all_audio)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(full_audio.astype(np.int16).tobytes())

        wav_bytes = wav_buffer.getvalue()
        duration = len(full_audio) / 16000

        file_path = db.audio_files.upload_audio(
            meeting_id, wav_bytes, "full_recording.wav"
        )

        db.audio_files.create(
            meeting_id=meeting_id,
            file_path=file_path,
            duration_seconds=duration,
            sample_rate=16000,
        )

        logger.info(f"Saved audio to Supabase: {file_path} ({duration:.1f}s)")

    except Exception as e:
        logger.error(f"Failed to save audio to Supabase: {e}")
