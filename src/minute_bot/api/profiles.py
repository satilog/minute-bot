"""Speaker profile enrollment and management endpoints."""

import logging

from apiflask import APIBlueprint
from flask import jsonify, request

from minute_bot.audio import decode_audio_base64
from minute_bot.services import registry

logger = logging.getLogger(__name__)

bp = APIBlueprint("profiles", __name__, url_prefix="/profiles", tag="profiles")


@bp.route("", methods=["GET"])
def list_profiles():
    """List all enrolled speaker profiles."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        profiles = db.speaker_profiles.list_all()
        return jsonify({"profiles": profiles, "count": len(profiles)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/enroll", methods=["POST"])
def enroll():
    """
    Enroll a speaker profile from a voice sample.

    Body: {name: str, audio_data: base64-encoded int16 PCM at 16kHz}
    Returns 503 if the diarization model is not yet ready.
    """
    if registry.diarizer is None:
        return jsonify({"error": "Diarization model not ready — try again in a moment"}), 503

    data = request.get_json()
    if not data or "name" not in data or "audio_data" not in data:
        return jsonify({"error": "Missing required fields: name, audio_data"}), 400

    name = data["name"].strip()
    if not name:
        return jsonify({"error": "name cannot be empty"}), 400

    try:
        audio = decode_audio_base64(data["audio_data"])
    except Exception as e:
        return jsonify({"error": f"Invalid audio_data: {e}"}), 400

    embedding = registry.diarizer.extract_embedding(audio)
    if embedding is None:
        return jsonify({
            "error": "Failed to extract voice embedding — audio may be too short or silent. "
                     "Record at least 5 seconds of clear speech."
        }), 422

    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        profile = db.speaker_profiles.create(name=name, voice_embedding=embedding)
        logger.info(f"Enrolled speaker profile: {name!r} ({profile.get('id')})")
        return jsonify({"status": "enrolled", "profile": profile}), 201
    except Exception as e:
        logger.error(f"Failed to save speaker profile: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/<profile_id>", methods=["DELETE"])
def delete_profile(profile_id: str):
    """Delete a speaker profile by ID."""
    try:
        from minute_bot.db import MinuteBotDB

        db = MinuteBotDB()
        deleted = db.speaker_profiles.delete(profile_id)
        if deleted:
            return jsonify({"status": "deleted", "id": profile_id})
        return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
