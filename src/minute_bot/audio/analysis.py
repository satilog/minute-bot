"""Audio analysis utilities."""

import numpy as np

from minute_bot.audio.processing import DEFAULT_SAMPLE_RATE


def compute_audio_duration(
    audio: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> float:
    """
    Compute duration of audio in seconds.

    Args:
        audio: Audio samples array.
        sample_rate: Sample rate in Hz.

    Returns:
        Duration in seconds.
    """
    return len(audio) / sample_rate


def compute_rms(audio: np.ndarray) -> float:
    """
    Compute RMS (root mean square) energy of audio.

    Args:
        audio: Audio samples.

    Returns:
        RMS value.
    """
    return np.sqrt(np.mean(audio.astype(np.float32) ** 2))


def extract_segment(
    audio: np.ndarray,
    start_time: float,
    end_time: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> np.ndarray:
    """
    Extract a time segment from audio array.

    Args:
        audio: Full audio array.
        start_time: Start time in seconds.
        end_time: End time in seconds.
        sample_rate: Sample rate of audio.

    Returns:
        Audio segment.
    """
    start_sample = int(start_time * sample_rate)
    end_sample = int(end_time * sample_rate)

    start_sample = max(0, start_sample)
    end_sample = min(len(audio), end_sample)

    return audio[start_sample:end_sample]


def detect_silence(
    audio: np.ndarray,
    threshold_db: float = -40.0,
    min_silence_ms: int = 500,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> list[tuple[float, float]]:
    """
    Detect silent regions in audio.

    Args:
        audio: Audio samples.
        threshold_db: Silence threshold in dB.
        min_silence_ms: Minimum silence duration in ms.
        sample_rate: Sample rate in Hz.

    Returns:
        List of (start_time, end_time) tuples for silent regions.
    """
    threshold_linear = 32768 * (10 ** (threshold_db / 20))
    frame_size = int(sample_rate * 0.01)  # 10ms frames

    silent_regions = []
    in_silence = False
    silence_start = 0

    for i in range(0, len(audio) - frame_size, frame_size):
        frame = audio[i : i + frame_size]
        rms = compute_rms(frame)

        frame_time = i / sample_rate

        if rms < threshold_linear:
            if not in_silence:
                in_silence = True
                silence_start = frame_time
        else:
            if in_silence:
                silence_end = frame_time
                if (silence_end - silence_start) * 1000 >= min_silence_ms:
                    silent_regions.append((silence_start, silence_end))
                in_silence = False

    # Handle trailing silence
    if in_silence:
        silence_end = len(audio) / sample_rate
        if (silence_end - silence_start) * 1000 >= min_silence_ms:
            silent_regions.append((silence_start, silence_end))

    return silent_regions


def split_on_silence(
    audio: np.ndarray,
    threshold_db: float = -40.0,
    min_silence_ms: int = 500,
    keep_silence_ms: int = 100,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> list[np.ndarray]:
    """
    Split audio on silent regions.

    Args:
        audio: Audio samples.
        threshold_db: Silence threshold in dB.
        min_silence_ms: Minimum silence duration to split on.
        keep_silence_ms: Amount of silence to keep at boundaries.
        sample_rate: Sample rate in Hz.

    Returns:
        List of audio segments.
    """
    silent_regions = detect_silence(audio, threshold_db, min_silence_ms, sample_rate)

    if not silent_regions:
        return [audio]

    keep_samples = int(keep_silence_ms * sample_rate / 1000)
    segments = []
    prev_end = 0

    for start, end in silent_regions:
        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)

        # Extract segment before silence
        seg_end = min(start_sample + keep_samples, len(audio))
        if seg_end > prev_end:
            segments.append(audio[prev_end:seg_end])

        prev_end = max(end_sample - keep_samples, 0)

    # Add final segment
    if prev_end < len(audio):
        segments.append(audio[prev_end:])

    return [seg for seg in segments if len(seg) > 0]
