"""Server-Sent Events endpoint for real-time meeting updates."""

import json
import logging
import queue
import threading
from typing import Generator

from apiflask import APIBlueprint
from flask import Response, request

from minute_bot.config import get_settings
from minute_bot.pubsub.client import get_redis_client

logger = logging.getLogger(__name__)

bp = APIBlueprint("events", __name__, tag="events")


@bp.route("/events/stream", methods=["GET"])
def stream_events():
    """
    SSE endpoint for real-time meeting event streaming.
    Connect with: GET /events/stream?session_id=<session_id>
    """
    session_id = request.args.get("session_id")
    if not session_id:
        return {"message": "session_id query parameter is required"}, 400

    settings = get_settings()
    event_queue: queue.Queue = queue.Queue(maxsize=100)
    stop_event = threading.Event()

    def redis_listener() -> None:
        """Background thread: subscribe to Redis channels and push events to queue."""
        # Create a dedicated Redis client for this SSE connection (not the shared one)
        redis_client = get_redis_client()
        pubsub = redis_client.pubsub()
        pubsub.subscribe(
            settings.transcript_channel,
            settings.diarization_channel,
            settings.graph_channel,
        )
        logger.info(
            "SSE listener started for session_id=%s on channels: %s, %s, %s",
            session_id,
            settings.transcript_channel,
            settings.diarization_channel,
            settings.graph_channel,
        )

        try:
            for message in pubsub.listen():
                if stop_event.is_set():
                    break

                if message["type"] != "message":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")

                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError as exc:
                    logger.error("Failed to decode Redis message on %s: %s", channel, exc)
                    continue

                # Filter by session_id when the message carries one
                msg_session = data.get("session_id")
                if msg_session and msg_session != session_id:
                    continue

                # Convert transcript segment
                if channel == settings.transcript_channel:
                    event = {
                        "type": "transcript",
                        "data": {
                            "text": data.get("text", ""),
                            "speaker_id": data.get("speaker_id"),
                            "speaker_label": data.get("speaker_label"),
                            "speaker_name": data.get("speaker_name"),
                            "start_time": data.get("start_time", 0.0),
                            "end_time": data.get("end_time", 0.0),
                        },
                    }

                # Convert diarization segment
                elif channel == settings.diarization_channel:
                    import uuid as _uuid
                    event = {
                        "type": "speaker",
                        "data": {
                            "id": data.get("speaker_id") or str(_uuid.uuid4()),
                            "speaker_label": data.get("speaker_label"),
                            "speaker_name": data.get("speaker_name"),
                            "profile_matched": data.get("profile_matched", False),
                        },
                    }

                # Graph channel: pass through as-is
                elif channel == settings.graph_channel:
                    event = data

                else:
                    continue

                try:
                    event_queue.put_nowait(json.dumps(event))
                except queue.Full:
                    logger.warning(
                        "SSE event queue full for session_id=%s, dropping event", session_id
                    )

        except Exception as exc:
            logger.error("SSE Redis listener error for session_id=%s: %s", session_id, exc)
        finally:
            pubsub.close()
            logger.info("SSE listener stopped for session_id=%s", session_id)

    listener_thread = threading.Thread(target=redis_listener, daemon=True)
    listener_thread.start()

    def generate() -> Generator[str, None, None]:
        """Generator that yields SSE-formatted strings to the client."""
        keepalive_counter = 0
        try:
            while True:
                try:
                    item = event_queue.get(timeout=15)
                    yield f"data: {item}\n\n"
                    keepalive_counter = 0
                except queue.Empty:
                    # Send a keepalive comment every ~15 seconds of idle time
                    keepalive_counter += 1
                    yield ": keepalive\n\n"
                    if keepalive_counter >= 2:
                        # After ~30 seconds with no data, reset counter (still alive)
                        keepalive_counter = 0
        except GeneratorExit:
            stop_event.set()
        except StopIteration:
            stop_event.set()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
