"""Audio pipeline internals and diagnostic endpoints."""

import io
import logging
import threading
import wave

import numpy as np
from apiflask import APIBlueprint
from flask import jsonify

from minute_bot.audio import decode_audio_base64
from minute_bot.config import get_settings
from minute_bot.core import get_audio_devices
from minute_bot.services import registry

logger = logging.getLogger(__name__)

bp = APIBlueprint("streaming", __name__, url_prefix="/streaming", tag="streaming")

# Accumulated raw audio for end-of-meeting WAV upload
_audio_accumulator: list = []
_accumulator_lock = threading.Lock()


def _publish_chunk(chunk: dict) -> None:
    """Publish an audio chunk to Redis and accumulate it for storage."""
    if registry.publisher:
        registry.publisher.publish_audio_chunk(chunk)

    if get_settings().save_audio_to_storage:
        with _accumulator_lock:
            _audio_accumulator.append(chunk["audio_data"])


def _save_audio_to_supabase(session_id: str, meeting_id: str) -> None:
    """Concatenate accumulated chunks and upload to Supabase Storage."""
    try:
        from minute_bot.db import MinuteBotDB
        db = MinuteBotDB()
    except Exception:
        return

    with _accumulator_lock:
        chunks = _audio_accumulator.copy()
        _audio_accumulator.clear()

    if not chunks:
        logger.warning("No audio chunks accumulated — nothing to save")
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

        file_path = db.audio_files.upload_audio(meeting_id, wav_bytes, "full_recording.wav")
        db.audio_files.create(
            meeting_id=meeting_id,
            file_path=file_path,
            duration_seconds=duration,
            sample_rate=16000,
        )
        logger.info(f"Audio saved: {file_path} ({duration:.1f}s)")

    except Exception as e:
        logger.error(f"Failed to save audio: {e}")


@bp.route("/devices", methods=["GET"])
def list_devices():
    """List available audio input devices (server-side, for diagnostics)."""
    try:
        devices = get_audio_devices()
        return jsonify({"devices": devices, "count": len(devices)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
