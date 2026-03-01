"""Audio manipulation and processing utilities."""

import numpy as np

from minute_bot.audio.encoding import decode_audio_base64

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
BYTES_PER_SAMPLE = 2  # 16-bit audio


def concatenate_chunks(chunks: list[str]) -> np.ndarray:
    """
    Concatenate multiple base64 audio chunks into single array.

    Args:
        chunks: List of base64 encoded audio chunks.

    Returns:
        Concatenated audio as numpy array.
    """
    arrays = [decode_audio_base64(chunk) for chunk in chunks]
    return np.concatenate(arrays)


def resample_audio(
    audio: np.ndarray,
    original_rate: int,
    target_rate: int,
) -> np.ndarray:
    """
    Resample audio to target sample rate using linear interpolation.

    Args:
        audio: Input audio samples.
        original_rate: Original sample rate in Hz.
        target_rate: Target sample rate in Hz.

    Returns:
        Resampled audio array.
    """
    if original_rate == target_rate:
        return audio

    duration = len(audio) / original_rate
    target_length = int(duration * target_rate)

    indices = np.linspace(0, len(audio) - 1, target_length)
    resampled = np.interp(indices, np.arange(len(audio)), audio.astype(np.float32))

    return resampled.astype(audio.dtype)


def normalize_audio(audio: np.ndarray, target_db: float = -20.0) -> np.ndarray:
    """
    Normalize audio to target dB level.

    Args:
        audio: Input audio samples.
        target_db: Target RMS level in dB.

    Returns:
        Normalized audio array.
    """
    audio_float = audio.astype(np.float32)

    rms = np.sqrt(np.mean(audio_float**2))
    if rms == 0:
        return audio

    current_db = 20 * np.log10(rms / 32768.0)
    gain = 10 ** ((target_db - current_db) / 20)

    normalized = audio_float * gain
    normalized = np.clip(normalized, -32768, 32767)

    return normalized.astype(np.int16)


def convert_to_mono(audio: np.ndarray, channels: int) -> np.ndarray:
    """
    Convert multi-channel audio to mono.

    Args:
        audio: Input audio samples (interleaved if stereo).
        channels: Number of channels in input.

    Returns:
        Mono audio array.
    """
    if channels == 1:
        return audio

    # Reshape to (samples, channels) and average
    audio_reshaped = audio.reshape(-1, channels)
    mono = audio_reshaped.mean(axis=1)

    return mono.astype(audio.dtype)
