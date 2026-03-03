"""Publisher helpers for knowledge graph events (entities, relationships, meeting events)."""

import json
import logging
from datetime import datetime, timezone

from minute_bot.config import get_settings
from minute_bot.pubsub.client import get_redis_client

logger = logging.getLogger(__name__)

_settings = get_settings()


def _publish(event_type: str, data: dict) -> None:
    """Publish a typed graph event to the graph channel."""
    try:
        client = get_redis_client()
        message = json.dumps({"type": event_type, "data": data})
        client.publish(_settings.graph_channel, message)
    except Exception as e:
        logger.error(f"Failed to publish graph event: {e}")


def publish_entity(entity_id: str, entity_type: str, entity_name: str) -> None:
    """Publish an entity SSE event. entity_type should be Title Case."""
    _publish("entity", {
        "id": entity_id,
        "entity_type": entity_type,
        "entity_name": entity_name,
    })


def publish_relationship(source_id: str, target_id: str, relationship_type: str) -> None:
    """Publish a relationship SSE event."""
    _publish("relationship", {
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "relationship_type": relationship_type,
    })


def publish_meeting_event(
    event_id: str,
    event_type: str,
    description: str,
    timestamp: str | None = None,
) -> None:
    """Publish a meeting event SSE event. event_type should be Title Case."""
    _publish("event", {
        "id": event_id,
        "event_type": event_type,
        "description": description,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    })


def publish_speaker(
    speaker_id: str,
    speaker_label: str,
    speaker_name: str,
    profile_matched: bool = False,
) -> None:
    """Publish a speaker SSE event when a new speaker is identified."""
    _publish("speaker", {
        "id": speaker_id,
        "speaker_label": speaker_label,
        "speaker_name": speaker_name,
        "profile_matched": profile_matched,
    })
