"""Audio buffer for accumulating chunks."""

import numpy as np

from minute_bot.audio.encoding import decode_audio_base64
from minute_bot.audio.processing import DEFAULT_SAMPLE_RATE


class AudioBuffer:
    """Buffer for accumulating audio chunks."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._buffer: list[np.ndarray] = []
        self._total_samples = 0

    def add_chunk(self, chunk: str) -> None:
        """Add a base64 encoded chunk to buffer."""
        audio = decode_audio_base64(chunk)
        self._buffer.append(audio)
        self._total_samples += len(audio)

    def get_audio(self) -> np.ndarray:
        """Get all buffered audio as single array."""
        if not self._buffer:
            return np.array([], dtype=np.int16)
        return np.concatenate(self._buffer)

    def get_duration(self) -> float:
        """Get buffered audio duration in seconds."""
        return self._total_samples / self.sample_rate

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()
        self._total_samples = 0

    def get_latest(self, duration_seconds: float) -> np.ndarray:
        """Get the latest N seconds of audio."""
        target_samples = int(duration_seconds * self.sample_rate)
        audio = self.get_audio()

        if len(audio) <= target_samples:
            return audio

        return audio[-target_samples:]
