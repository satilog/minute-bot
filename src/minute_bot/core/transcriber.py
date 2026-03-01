"""Whisper-based speech transcription."""

import logging
import uuid
from typing import Optional

import numpy as np
import whisper

from minute_bot.config import get_settings

logger = logging.getLogger(__name__)


class Transcriber:
    """Whisper-based speech-to-text transcription."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        language: Optional[str] = None,
    ):
        """
        Initialize transcriber.

        Args:
            model_name: Whisper model name (tiny, base, small, medium, large).
            language: Language code for transcription.
        """
        settings = get_settings()
        self.model_name = model_name or settings.whisper_model
        self.language = language or settings.language
        self._model: Optional[whisper.Whisper] = None

    @property
    def model(self) -> whisper.Whisper:
        """Lazy-load Whisper model."""
        if self._model is None:
            logger.info(f"Loading Whisper model: {self.model_name}")
            self._model = whisper.load_model(self.model_name)
            logger.info("Whisper model loaded successfully")
        return self._model

    def transcribe(
        self,
        audio: np.ndarray,
        session_id: str,
    ) -> list[dict]:
        """
        Transcribe audio using Whisper.

        Args:
            audio: Audio samples (16kHz, mono, int16).
            session_id: Session identifier.

        Returns:
            List of transcription segment dictionaries.
        """
        # Convert to float32 and normalize for Whisper
        audio_float = audio.astype(np.float32) / 32768.0

        # Transcribe with word timestamps
        result = self.model.transcribe(
            audio_float,
            language=self.language,
            word_timestamps=True,
            fp16=False,
        )

        segments = []
        for seg in result.get("segments", []):
            segment_id = str(uuid.uuid4())

            words = []
            for word_info in seg.get("words", []):
                words.append(
                    {
                        "word": word_info["word"].strip(),
                        "start_time": word_info["start"],
                        "end_time": word_info["end"],
                        "confidence": word_info.get("probability", 1.0),
                    }
                )

            segments.append(
                {
                    "session_id": session_id,
                    "segment_id": segment_id,
                    "text": seg["text"].strip(),
                    "start_time": seg["start"],
                    "end_time": seg["end"],
                    "words": words,
                    "language": result.get("language", self.language),
                    "confidence": seg.get("avg_logprob", 0.0),
                }
            )

        return segments


def get_available_models() -> list[str]:
    """Get list of available Whisper models."""
    return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
