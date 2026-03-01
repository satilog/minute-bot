"""Audio encoding and decoding utilities."""

import base64

import numpy as np


def encode_audio_base64(audio_data: np.ndarray) -> str:
    """
    Encode numpy audio array to base64 string.

    Args:
        audio_data: Audio samples as numpy array (int16).

    Returns:
        Base64 encoded string of audio bytes.
    """
    audio_bytes = audio_data.astype(np.int16).tobytes()
    return base64.b64encode(audio_bytes).decode("utf-8")


def decode_audio_base64(encoded: str, dtype: np.dtype = np.int16) -> np.ndarray:
    """
    Decode base64 string to numpy audio array.

    Args:
        encoded: Base64 encoded audio data.
        dtype: Numpy dtype for the output array.

    Returns:
        Audio samples as numpy array.
    """
    audio_bytes = base64.b64decode(encoded)
    return np.frombuffer(audio_bytes, dtype=dtype)
