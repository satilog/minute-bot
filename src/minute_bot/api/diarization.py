"""Diarization processing — auto-started at server boot."""

import logging
from datetime import datetime, timezone
from typing import Optional

from apiflask import APIBlueprint
from flask import jsonify, request

from minute_bot.config import get_settings
from minute_bot.core import AudioBuffer
from minute_bot.pubsub import Subscriber
from minute_bot.services import registry

logger = logging.getLogger(__name__)

bp = APIBlueprint("diarization", __name__, url_prefix="/diarization", tag="diarization")

# Internal state
_subscriber: Optional[Subscriber] = None
_is_processing = False
_audio_buffers: dict[str, AudioBuffer] = {}
_session_meeting_map: dict[str, str] = {}
_session_speakers: dict[str, dict[str, str]] = {}

# Stores diarization segment timing per session so the post-processing
# attribution job can match transcript chunks to speakers by time overlap.
# Each entry: {speaker_id (DB UUID), start_time (float), end_time (float)}.
# Consumed and cleared by get_and_clear_segments() after meeting stop.
_session_segments: dict[str, list[dict]] = {}

_processing_stats = {
    "chunks_received": 0,
    "segments_processed": 0,
    "speakers_identified": 0,
    "errors": 0,
}


def _init_processing() -> None:
    """Start the diarization subscriber. Called automatically at server startup."""
    global _subscriber, _is_processing

    _subscriber = Subscriber()
    _subscriber.subscribe_audio(_handle_audio_chunk)
    _subscriber.start()
    _is_processing = True
    logger.info("[startup:diarization] Subscriber started")


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


def _get_or_create_speaker(
    session_id: str,
    speaker_label: str,
    meeting_id: str,
    audio=None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    sample_rate: int = 16000,
) -> Optional[str]:
    if session_id not in _session_speakers:
        _session_speakers[session_id] = {}

    speakers = _session_speakers[session_id]
    if speaker_label in speakers:
        return speakers[speaker_label]

    # Attempt to match this speaker against global profiles via voice embedding.
    # Only runs once per speaker label per session (result is cached above).
    resolved_name = speaker_label
    resolved_profile_id = None
    embedding = None

    if audio is not None and start_time is not None and end_time is not None and registry.diarizer is not None:
        try:
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            segment_audio = audio[start_sample:end_sample]

            embedding = registry.diarizer.extract_embedding(segment_audio)
            if embedding:
                from minute_bot.db import MinuteBotDB

                db = MinuteBotDB()
                matches = db.speaker_profiles.find_by_embedding(embedding, threshold=0.7)
                if matches:
                    resolved_name = matches[0]["name"]
                    resolved_profile_id = matches[0]["id"]
                    logger.info(
                        f"Speaker {speaker_label} matched profile {resolved_name!r} "
                        f"(similarity={matches[0]['similarity']:.3f})"
                    )
        except Exception as e:
            logger.error(f"Profile matching failed for {speaker_label}: {e}")

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        speaker = db.speakers.create(
            meeting_id=meeting_id,
            speaker_label=speaker_label,
            speaker_name=resolved_name,
            voice_embedding=embedding,
            profile_id=resolved_profile_id,
        )
        speaker_id = speaker.get("id")
        speakers[speaker_label] = speaker_id
        return speaker_id
    except Exception as e:
        logger.error(f"Failed to create speaker: {e}")
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
        if buffer.get_duration() >= settings.diarization_buffer_duration:
            if registry.diarizer is None:
                logger.warning("[diarization] Pyannote not yet ready, skipping chunk")
                return

            audio = buffer.get_audio()
            buffer.clear()

            segments = registry.diarizer.diarize(audio, session_id)
            meeting_id = _get_meeting_id(session_id)

            if registry.publisher:
                for segment in segments:
                    segment["timestamp"] = datetime.now(timezone.utc).isoformat()
                    registry.publisher.publish_diarization(segment)
                    _processing_stats["segments_processed"] += 1

                    if meeting_id:
                        speaker_id = _get_or_create_speaker(
                            session_id,
                            segment["speaker_id"],
                            meeting_id,
                            audio=audio,
                            start_time=segment["start_time"],
                            end_time=segment["end_time"],
                        )
                        if speaker_id:
                            _update_speaker_time(
                                speaker_id, segment["end_time"] - segment["start_time"]
                            )
                            # Record timing so attribution can match transcripts later
                            _session_segments.setdefault(session_id, []).append({
                                "speaker_id": speaker_id,
                                "start_time": segment["start_time"],
                                "end_time": segment["end_time"],
                            })

            logger.debug(f"Diarized {len(segments)} segments for session {session_id}")

    except Exception as e:
        _processing_stats["errors"] += 1
        logger.error(f"Error processing chunk for diarization: {e}")


def get_and_clear_segments(session_id: str) -> list[dict]:
    """Return all recorded diarization segments for a session and clear them.

    Called by the speaker attribution job after meeting stop.  Returns a list
    of dicts: [{speaker_id, start_time, end_time}, ...] sorted by start_time.
    """
    return _session_segments.pop(session_id, [])


def _update_speaker_time(speaker_id: str, duration: float) -> None:
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        db.speakers.update_speaking_time(speaker_id, duration)
    except Exception as e:
        logger.error(f"Failed to update speaker time: {e}")


@bp.route("/status", methods=["GET"])
def get_status():
    """Diagnostic: diarization pipeline state."""
    settings = get_settings()
    return jsonify({
        "is_processing": _is_processing,
        "model_status": registry.get_status().get("pyannote"),
        "buffer_duration": settings.diarization_buffer_duration,
        "min_speakers": settings.min_speakers,
        "max_speakers": settings.max_speakers,
        "stats": _processing_stats,
        "active_sessions": list(_audio_buffers.keys()),
    })
