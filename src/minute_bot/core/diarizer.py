"""Pyannote-based speaker diarization."""

import logging
import os
import uuid
from typing import Optional

import numpy as np
import torch

from minute_bot.config import get_settings

logger = logging.getLogger(__name__)


class Diarizer:
    """Pyannote-based speaker diarization."""

    def __init__(
        self,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
        hf_token: Optional[str] = None,
    ):
        """
        Initialize diarizer.

        Args:
            min_speakers: Minimum expected speakers.
            max_speakers: Maximum expected speakers.
            hf_token: HuggingFace token for pyannote models.
        """
        settings = get_settings()
        self.min_speakers = min_speakers or settings.min_speakers
        self.max_speakers = max_speakers or settings.max_speakers
        self.hf_token = hf_token or settings.hf_token
        self._pipeline = None
        self._embedding_model = None

    @property
    def pipeline(self):
        """Lazy-load diarization pipeline."""
        if self._pipeline is None:
            from pyannote.audio import Pipeline

            logger.info("Loading pyannote diarization pipeline")
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token,
            )

            if torch.cuda.is_available():
                self._pipeline = self._pipeline.to(torch.device("cuda"))
                logger.info("Using CUDA for diarization")

            logger.info("Diarization pipeline loaded")

        return self._pipeline

    @property
    def embedding_model(self):
        """Lazy-load speaker embedding model."""
        if self._embedding_model is None:
            from pyannote.audio import Model

            logger.info("Loading speaker embedding model")
            self._embedding_model = Model.from_pretrained(
                "pyannote/embedding",
                use_auth_token=self.hf_token,
            )

            if torch.cuda.is_available():
                self._embedding_model = self._embedding_model.to(torch.device("cuda"))

            logger.info("Embedding model loaded")

        return self._embedding_model

    def diarize(
        self,
        audio: np.ndarray,
        session_id: str,
        sample_rate: int = 16000,
    ) -> list[dict]:
        """
        Perform speaker diarization on audio.

        Args:
            audio: Audio samples (int16).
            session_id: Session identifier.
            sample_rate: Audio sample rate.

        Returns:
            List of speaker segment dictionaries.
        """
        # Convert to float32 and normalize
        audio_float = audio.astype(np.float32) / 32768.0

        # Create audio tensor for pyannote
        waveform = torch.tensor(audio_float).unsqueeze(0)

        # Run diarization
        diarization = self.pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
        )

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segment_id = str(uuid.uuid4())
            segments.append(
                {
                    "session_id": session_id,
                    "segment_id": segment_id,
                    "speaker_id": speaker,
                    "start_time": turn.start,
                    "end_time": turn.end,
                    "duration": turn.end - turn.start,
                }
            )

        return segments

    def extract_embedding(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[list[float]]:
        """
        Extract speaker embedding from audio.

        Args:
            audio: Audio samples (int16).
            sample_rate: Audio sample rate.

        Returns:
            Speaker embedding as list of floats, or None on failure.
        """
        from pyannote.audio import Inference

        try:
            inference = Inference(
                self.embedding_model,
                window="whole",
            )

            audio_float = audio.astype(np.float32) / 32768.0
            waveform = torch.tensor(audio_float).unsqueeze(0)

            embedding = inference({"waveform": waveform, "sample_rate": sample_rate})
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Failed to extract embedding: {e}")
            return None
