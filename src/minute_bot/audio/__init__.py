"""Audio processing utilities."""

from minute_bot.audio.encoding import (
    decode_audio_base64,
    encode_audio_base64,
)
from minute_bot.audio.processing import (
    BYTES_PER_SAMPLE,
    DEFAULT_CHANNELS,
    DEFAULT_SAMPLE_RATE,
    concatenate_chunks,
    convert_to_mono,
    normalize_audio,
    resample_audio,
)
from minute_bot.audio.analysis import (
    compute_audio_duration,
    compute_rms,
    detect_silence,
    extract_segment,
    split_on_silence,
)

__all__ = [
    # Constants
    "BYTES_PER_SAMPLE",
    "DEFAULT_CHANNELS",
    "DEFAULT_SAMPLE_RATE",
    # Encoding
    "decode_audio_base64",
    "encode_audio_base64",
    # Processing
    "concatenate_chunks",
    "convert_to_mono",
    "normalize_audio",
    "resample_audio",
    # Analysis
    "compute_audio_duration",
    "compute_rms",
    "detect_silence",
    "extract_segment",
    "split_on_silence",
]
