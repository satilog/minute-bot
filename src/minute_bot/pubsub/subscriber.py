"""Redis subscriber for audio and transcription data."""

import json
import logging
import threading
from typing import Callable, Optional

import redis

from minute_bot.config import get_settings
from minute_bot.pubsub.client import get_redis_client

logger = logging.getLogger(__name__)


class Subscriber:
    """Subscribes to Redis channels and dispatches messages."""

    def __init__(self, client: redis.Redis = None):
        self.client = client or get_redis_client()
        self._settings = get_settings()
        self._pubsub: Optional[redis.client.PubSub] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._handlers: dict[str, Callable[[dict], None]] = {}

    def subscribe(
        self,
        channel: str,
        handler: Callable[[dict], None],
    ) -> None:
        """
        Subscribe to a channel with a message handler.

        Args:
            channel: Redis channel name.
            handler: Callback function for messages.
        """
        self._handlers[channel] = handler

    def subscribe_audio(self, handler: Callable[[dict], None]) -> None:
        """Subscribe to audio channel."""
        self.subscribe(self._settings.audio_channel, handler)

    def subscribe_transcripts(self, handler: Callable[[dict], None]) -> None:
        """Subscribe to transcript channel."""
        self.subscribe(self._settings.transcript_channel, handler)

    def subscribe_diarization(self, handler: Callable[[dict], None]) -> None:
        """Subscribe to diarization channel."""
        self.subscribe(self._settings.diarization_channel, handler)

    def start(self) -> None:
        """Start listening for messages in a background thread."""
        if self._thread and self._thread.is_alive():
            return

        if not self._handlers:
            logger.warning("No handlers registered, not starting subscriber")
            return

        self._pubsub = self.client.pubsub()
        self._pubsub.subscribe(*self._handlers.keys())

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        logger.info(f"Subscriber started for channels: {list(self._handlers.keys())}")

    def stop(self) -> None:
        """Stop listening for messages."""
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        if self._pubsub:
            self._pubsub.close()
            self._pubsub = None

        logger.info("Subscriber stopped")

    def _listen_loop(self) -> None:
        """Main message listening loop."""
        for message in self._pubsub.listen():
            if self._stop_event.is_set():
                break

            if message["type"] != "message":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            handler = self._handlers.get(channel)
            if not handler:
                continue

            try:
                data = json.loads(message["data"])
                handler(data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode message on {channel}: {e}")
            except Exception as e:
                logger.error(f"Handler error on {channel}: {e}")
