"""Health check endpoints."""

import logging

from apiflask import APIBlueprint
from flask import jsonify

logger = logging.getLogger(__name__)

bp = APIBlueprint("health", __name__, tag="health")


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint — includes model initialization status."""
    from minute_bot.pubsub import get_redis_client
    from minute_bot.services import registry

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

        get_supabase_client()
        supabase_ok = True
    except Exception:
        pass

    service_status = registry.get_status()
    all_ready = registry.is_ready

    return jsonify(
        {
            "status": "ok" if all_ready else "error",
            "service": "minute-bot",
            "redis_connected": redis_ok,
            "supabase_connected": supabase_ok,
            "models": service_status,
        }
    )
