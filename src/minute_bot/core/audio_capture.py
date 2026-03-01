"""Audio capture module for microphone input streaming."""

import base64
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np
import pyaudio

from minute_bot.audio.processing import resample_audio


class AudioCapture:
    """Handles microphone audio capture with threaded streaming."""

    SAMPLE_RATE = 16000  # Target rate for Whisper/pyannote
    CHANNELS = 1
    FORMAT = pyaudio.paInt16
    CHUNK_SIZE = 4096

    def __init__(self, on_chunk: Optional[Callable[[dict], None]] = None):
        """
        Initialize audio capture.

        Args:
            on_chunk: Callback function called with each audio chunk dict.
        """
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._stop_event = threading.Event()
        self._on_chunk = on_chunk
        self._session_id: Optional[str] = None
        self._chunk_index = 0
        self._audio_queue: queue.Queue = queue.Queue()
        self._capture_rate: int = self.SAMPLE_RATE  # actual hardware rate

    @property
    def is_running(self) -> bool:
        """Return whether audio capture is currently active."""
        return self._is_running

    @property
    def session_id(self) -> Optional[str]:
        """Return current capture session ID."""
        return self._session_id

    def _detect_capture_rate(self, p: pyaudio.PyAudio) -> int:
        """Return the default input device's native sample rate."""
        try:
            info = p.get_default_input_device_info()
            return int(info["defaultSampleRate"])
        except Exception:
            return self.SAMPLE_RATE

    def start(self) -> str:
        """
        Start audio capture.

        Returns:
            Session ID for this capture session.

        Raises:
            RuntimeError: If capture is already running.
        """
        if self._is_running:
            raise RuntimeError("Audio capture is already running")

        self._session_id = str(uuid.uuid4())
        self._chunk_index = 0
        self._stop_event.clear()

        self._pyaudio = pyaudio.PyAudio()
        self._capture_rate = self._detect_capture_rate(self._pyaudio)

        self._stream = self._pyaudio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self._capture_rate,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE,
        )

        self._is_running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        return self._session_id

    def stop(self) -> None:
        """Stop audio capture and clean up resources."""
        if not self._is_running:
            return

        self._stop_event.set()
        self._is_running = False

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None

        self._session_id = None

    def _capture_loop(self) -> None:
        """Main capture loop running in separate thread."""
        while not self._stop_event.is_set():
            try:
                audio_data = self._stream.read(
                    self.CHUNK_SIZE, exception_on_overflow=False
                )
                chunk = self._create_chunk(audio_data)

                if self._on_chunk:
                    self._on_chunk(chunk)

                self._audio_queue.put(chunk)
                self._chunk_index += 1

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"Audio capture error: {e}")
                break

    def _create_chunk(self, audio_data: bytes) -> dict:
        """
        Create a chunk dictionary from raw audio data, resampling to SAMPLE_RATE
        if the hardware capture rate differs.

        Args:
            audio_data: Raw PCM audio bytes captured at self._capture_rate.

        Returns:
            Dictionary with chunk metadata and base64-encoded audio at SAMPLE_RATE.
        """
        audio = np.frombuffer(audio_data, dtype=np.int16)

        if self._capture_rate != self.SAMPLE_RATE:
            audio = resample_audio(audio, self._capture_rate, self.SAMPLE_RATE)

        return {
            "session_id": self._session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chunk_index": self._chunk_index,
            "sample_rate": self.SAMPLE_RATE,
            "channels": self.CHANNELS,
            "format": "int16",
            "audio_data": base64.b64encode(audio.astype(np.int16).tobytes()).decode("utf-8"),
        }

    def get_chunk(self, timeout: float = 1.0) -> Optional[dict]:
        """
        Get the next audio chunk from the queue.

        Args:
            timeout: Maximum time to wait for a chunk.

        Returns:
            Audio chunk dict or None if timeout.
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_status(self) -> dict:
        """Return current capture status."""
        return {
            "is_running": self._is_running,
            "session_id": self._session_id,
            "chunk_index": self._chunk_index,
            "sample_rate": self.SAMPLE_RATE,
            "capture_rate": self._capture_rate,
            "channels": self.CHANNELS,
            "chunk_size": self.CHUNK_SIZE,
        }


def get_audio_devices() -> list[dict]:
    """
    List available audio input devices.

    Returns:
        List of device info dictionaries.
    """
    p = pyaudio.PyAudio()
    devices = []

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            devices.append(
                {
                    "index": i,
                    "name": info["name"],
                    "channels": info["maxInputChannels"],
                    "sample_rate": int(info["defaultSampleRate"]),
                }
            )

    p.terminate()
    return devices
