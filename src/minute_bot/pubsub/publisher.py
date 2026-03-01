"""Redis publisher for audio and transcription data."""

import json
import logging
from typing import Any

import redis

from minute_bot.config import get_settings
from minute_bot.pubsub.client import get_redis_client

logger = logging.getLogger(__name__)


class Publisher:
    """Publishes messages to Redis channels."""

    def __init__(self, client: redis.Redis = None):
        self.client = client or get_redis_client()
        self._settings = get_settings()

    def publish(self, channel: str, message: dict) -> int:
        """
        Publish a message to a channel.

        Args:
            channel: Redis channel name.
            message: Message dict to publish (will be JSON encoded).

        Returns:
            Number of subscribers that received the message.
        """
        try:
            return self.client.publish(channel, json.dumps(message))
        except redis.RedisError as e:
            logger.error(f"Redis publish error on {channel}: {e}")
            return 0

    def publish_audio_chunk(self, chunk: dict) -> int:
        """Publish audio chunk to audio channel."""
        return self.publish(self._settings.audio_channel, chunk)

    def publish_transcript(self, segment: dict) -> int:
        """Publish transcript segment to transcript channel."""
        return self.publish(self._settings.transcript_channel, segment)

    def publish_diarization(self, segment: dict) -> int:
        """Publish diarization segment to diarization channel."""
        return self.publish(self._settings.diarization_channel, segment)
