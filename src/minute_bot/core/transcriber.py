"""Speech transcription using faster-whisper (CTranslate2-based Whisper).

faster-whisper runs the same Whisper model weights as openai-whisper but via
CTranslate2's int8 quantization, giving ~4x faster CPU inference and ~50% less
memory without sacrificing accuracy.

Model recommendations (set WHISPER_MODEL in .env):
    large-v3          -- best accuracy, ~2 GB VRAM/RAM  (recommended with GPU)
    large-v3-turbo    -- large-v3 quality at ~2x the speed
    distil-large-v3   -- fastest large model, English-only
    medium            -- good balance for CPU-only setups
    base              -- legacy default; lowest accuracy
"""

import logging
import uuid
from typing import Optional

import numpy as np

from minute_bot.config import get_settings

logger = logging.getLogger(__name__)


class Transcriber:
    """faster-whisper speech-to-text transcription.

    Lazy-loads the model on first call to avoid blocking server startup.
    Automatically selects float16 on CUDA or int8 on CPU.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        language: Optional[str] = None,
    ):
        settings = get_settings()
        self.model_name = model_name or settings.whisper_model
        self.language = language or settings.language
        self._model = None

    @property
    def model(self):
        """Lazy-load the faster-whisper model on first access."""
        if self._model is None:
            import torch
            from faster_whisper import WhisperModel

            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

            logger.info(
                "Loading faster-whisper model: %s (device=%s, compute_type=%s)",
                self.model_name, device, compute_type,
            )
            self._model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute_type,
            )
            logger.info("faster-whisper model loaded successfully")
        return self._model

    def transcribe(
        self,
        audio: np.ndarray,
        session_id: str,
    ) -> list[dict]:
        """Transcribe audio using faster-whisper.

        Args:
            audio:      Audio samples (16 kHz, mono, int16).
            session_id: Session identifier forwarded into each segment dict.

        Returns:
            List of segment dicts containing:
                session_id, segment_id, text, start_time, end_time,
                words, language, confidence
        """
        # faster-whisper expects float32 normalised to [-1.0, 1.0]
        audio_float = audio.astype(np.float32) / 32768.0

        rms = float(np.sqrt(np.mean(audio_float ** 2)))
        peak = float(np.max(np.abs(audio_float)))
        duration_s = len(audio_float) / 16000.0

        logger.info(
            "[transcriber] input  dtype=%s  shape=%s  duration=%.2fs  rms=%.4f  peak=%.4f  model=%s  lang=%s",
            audio.dtype, audio.shape, duration_s, rms, peak, self.model_name, self.language,
        )

        if peak < 0.001:
            logger.warning("[transcriber] Audio is nearly silent (peak=%.5f) — transcription will likely be empty", peak)

        segments_gen, info = self.model.transcribe(
            audio_float,
            language=self.language,
            word_timestamps=True,
            beam_size=5,
            # vad_filter is intentionally OFF for streaming chunks: silero-VAD
            # rejects entire 5-second windows that start/end with silence, causing
            # zero output with no error.  The buffer threshold already handles
            # accumulation; silence rejection is not needed at this layer.
        )

        logger.info(
            "[transcriber] model returned — detected lang=%s (prob=%.2f)  duration=%.2fs",
            info.language, info.language_probability, info.duration,
        )

        segments = []
        for seg in segments_gen:
            text = seg.text.strip()
            logger.info(
                "[transcriber] raw segment  %.2f-%.2fs  logprob=%.3f  no_speech=%.3f  text=%r",
                seg.start, seg.end, seg.avg_logprob, seg.no_speech_prob, text[:100],
            )
            if not text:
                continue

            words = [
                {
                    "word": w.word.strip(),
                    "start_time": w.start,
                    "end_time": w.end,
                    "confidence": w.probability,
                }
                for w in (seg.words or [])
            ]

            segments.append(
                {
                    "session_id": session_id,
                    "segment_id": str(uuid.uuid4()),
                    "text": text,
                    "start_time": seg.start,
                    "end_time": seg.end,
                    "words": words,
                    "language": info.language,
                    "confidence": seg.avg_logprob,
                }
            )

        logger.info("[transcriber] returning %d segment(s) for session %s", len(segments), session_id[:8])
        return segments


def get_available_models() -> list[str]:
    """Return faster-whisper compatible model identifiers."""
    return [
        "tiny", "base", "small", "medium",
        "large-v2", "large-v3", "large-v3-turbo", "distil-large-v3",
    ]
