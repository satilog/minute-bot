"""Health check endpoints."""

import logging

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint("health", __name__)


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    from minute_bot.pubsub import get_redis_client

    redis_ok = False
    supabase_ok = False

    try:
        client = get_redis_client()
        client.ping()
        redis_ok = True
    except Exception:
        pass

    try:
        from minute_bot.db import get_supabase_client

        client = get_supabase_client()
        # Simple query to check connection
        supabase_ok = True
    except Exception:
        pass

    return jsonify(
        {
            "status": "healthy",
            "service": "minute-bot",
            "redis_connected": redis_ok,
            "supabase_connected": supabase_ok,
        }
    )
