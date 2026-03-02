"""Central service registry — initialized once at server startup."""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Holds all ML model instances and shared infrastructure.

    Models are loaded eagerly in background threads at startup so the
    HTTP server is immediately available while initialization proceeds.
    Processing handlers check for None before using a model and log a
    warning if a chunk arrives before the model is ready.
    """

    def __init__(self):
        self.transcriber = None
        self.diarizer = None
        self.publisher = None
        self._status = {
            "whisper": "pending",
            "pyannote": "pending",
            "pubsub": "pending",
        }

    def initialize(self) -> None:
        """Start background initialization of all services."""
        logger.info("=" * 60)
        logger.info("  Minute Bot — initializing services")
        logger.info("=" * 60)

        self._init_publisher()

        threading.Thread(
            target=self._load_whisper, daemon=True, name="init-whisper"
        ).start()
        threading.Thread(
            target=self._load_pyannote, daemon=True, name="init-pyannote"
        ).start()

    def _init_publisher(self) -> None:
        from minute_bot.pubsub import Publisher

        try:
            logger.info("[startup:pubsub] Connecting to Redis...")
            self.publisher = Publisher()
            self._status["pubsub"] = "ready"
            logger.info("[startup:pubsub] Redis connection ready")
        except Exception as e:
            self._status["pubsub"] = "error"
            logger.error(f"[startup:pubsub] Failed to connect: {e}")

    def _load_whisper(self) -> None:
        from minute_bot.core import Transcriber

        self._status["whisper"] = "loading"
        logger.info("[startup:whisper] Loading Whisper model...")
        try:
            self.transcriber = Transcriber()
            _ = self.transcriber.model  # trigger eager load
            self._status["whisper"] = "ready"
            logger.info("[startup:whisper] Whisper model ready")
        except Exception as e:
            self._status["whisper"] = "error"
            logger.error(f"[startup:whisper] Failed to load: {e}")

    def _load_pyannote(self) -> None:
        from minute_bot.core import Diarizer

        self._status["pyannote"] = "loading"
        logger.info("[startup:pyannote] Loading Pyannote diarization pipeline...")
        try:
            self.diarizer = Diarizer()
            _ = self.diarizer.pipeline       # trigger eager load
            _ = self.diarizer.embedding_model  # trigger eager load
            self._status["pyannote"] = "ready"
            logger.info("[startup:pyannote] Pyannote pipeline ready")
        except Exception as e:
            self._status["pyannote"] = "error"
            logger.error(f"[startup:pyannote] Failed to load: {e}")

    def get_status(self) -> dict:
        return dict(self._status)

    @property
    def is_ready(self) -> bool:
        return all(v == "ready" for v in self._status.values())


# Module-level singleton — imported by all modules that need services
registry = ServiceRegistry()
