#!/usr/bin/env python3
"""
Minute Bot Audio Client

Captures audio from your microphone on the host machine and streams it
to the Minute Bot server. Run this instead of relying on Docker mic access.

Usage:
    python client.py                          # auto-detect HyperX, prompt for title
    python client.py --title "Standup"        # set title up front
    python client.py --list-devices           # show all available input devices
    python client.py --device 2              # use a specific device by index
    python client.py --server http://host:5000  # custom server URL
    python client.py --enroll "Alice"         # record 10s voice sample and enroll as a profile

Requirements (install on host):
    pip install pyaudio numpy requests
"""

import argparse
import base64
import signal
import sys

import numpy as np
import pyaudio
import requests

DEFAULT_SERVER = "http://localhost:5000"
TARGET_RATE = 16000   # Whisper/pyannote expect 16kHz
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 4096
ENROLL_DURATION = 10  # seconds of audio to capture during enrollment


# ---------------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------------

def list_devices(p: pyaudio.PyAudio) -> None:
    print("\nAvailable input devices:")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"  [{i:2d}] {info['name']:<40}  "
                  f"{int(info['defaultSampleRate'])}Hz  "
                  f"{info['maxInputChannels']}ch")
    print()


def find_device_by_keyword(p: pyaudio.PyAudio, keyword: str) -> tuple[int | None, dict | None]:
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0 and keyword.lower() in info["name"].lower():
            return i, info
    return None, None


def supports_rate(p: pyaudio.PyAudio, device_index: int, rate: int) -> bool:
    try:
        p.is_format_supported(
            rate,
            input_device=device_index,
            input_channels=CHANNELS,
            input_format=FORMAT,
        )
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Audio resampling (host-side, no scipy needed)
# ---------------------------------------------------------------------------

def resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    new_len = int(len(audio) * to_rate / from_rate)
    resampled = np.interp(
        np.linspace(0, len(audio) - 1, new_len),
        np.arange(len(audio)),
        audio.astype(np.float64),
    )
    return resampled.astype(np.int16)


# ---------------------------------------------------------------------------
# Speaker enrollment
# ---------------------------------------------------------------------------

def enroll_speaker(name: str, server: str, p: pyaudio.PyAudio, device_index: int, device_info: dict) -> None:
    """Record ENROLL_DURATION seconds of audio and POST it to /profiles/enroll."""
    print(f"\nEnrolling voice profile for: {name!r}")

    # Check server health
    try:
        resp = requests.get(f"{server}/health", timeout=5)
        health = resp.json()
        models = health.get("models", {})
        pyannote_status = models.get("pyannote", "unknown")
        if pyannote_status != "ready":
            print(f"Warning: diarization model is '{pyannote_status}' — enrollment may fail.")
            print("Wait for model to finish loading and try again.\n")
    except Exception as e:
        print(f"Cannot reach server at {server}: {e}")
        return

    native_rate = int(device_info["defaultSampleRate"])
    capture_rate = TARGET_RATE if supports_rate(p, device_index, TARGET_RATE) else native_rate

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=capture_rate,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK_SIZE,
    )

    total_samples = ENROLL_DURATION * capture_rate
    collected = 0
    frames: list[np.ndarray] = []

    print(f"Recording {ENROLL_DURATION}s at {capture_rate}Hz — speak clearly now...\n")

    while collected < total_samples:
        raw = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        chunk = np.frombuffer(raw, dtype=np.int16)
        frames.append(chunk)
        collected += len(chunk)

        # Level meter
        rms = int(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        filled = min(40, rms // 80)
        bar = "█" * filled + "░" * (40 - filled)
        remaining = max(0, (total_samples - collected) / capture_rate)
        print(f"\r  [{bar}] {remaining:.1f}s left ", end="", flush=True)

    print("\n\nCapture complete. Sending to server...")
    stream.stop_stream()
    stream.close()

    audio = np.concatenate(frames)
    if capture_rate != TARGET_RATE:
        audio = resample(audio, capture_rate, TARGET_RATE)

    audio_b64 = base64.b64encode(audio.astype(np.int16).tobytes()).decode()

    try:
        resp = requests.post(
            f"{server}/profiles/enroll",
            json={"name": name, "audio_data": audio_b64},
            timeout=30,
        )
        if resp.status_code == 201:
            profile = resp.json().get("profile", {})
            print(f"Enrolled successfully!")
            print(f"  Profile ID : {profile.get('id')}")
            print(f"  Name       : {profile.get('name')}")
        else:
            print(f"Enrollment failed ({resp.status_code}): {resp.json().get('error', resp.text)}")
    except Exception as e:
        print(f"Request failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Minute Bot Audio Client")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--title", default=None)
    parser.add_argument("--device", type=int, default=None,
                        help="Input device index (overrides auto-detect)")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--enroll", metavar="NAME",
                        help=f"Record a {ENROLL_DURATION}s voice sample and enroll it as a speaker profile")
    args = parser.parse_args()

    p = pyaudio.PyAudio()

    if args.list_devices:
        list_devices(p)
        p.terminate()
        return

    # ---- Select microphone ------------------------------------------------
    if args.device is not None:
        device_index = args.device
        device_info = p.get_device_info_by_index(device_index)
        print(f"Using device [{device_index}]: {device_info['name']}")
    else:
        device_index, device_info = find_device_by_keyword(p, "hyperx")
        if device_index is not None:
            print(f"Found HyperX device [{device_index}]: {device_info['name']}")
        else:
            device_info = p.get_default_input_device_info()
            device_index = int(device_info["index"])
            print(f"HyperX not found. Using default [{device_index}]: {device_info['name']}")
            print("Tip: run --list-devices to see all inputs, --device N to select one.\n")

    # ---- Enrollment mode --------------------------------------------------
    if args.enroll:
        enroll_speaker(args.enroll, args.server, p, device_index, device_info)
        p.terminate()
        return

    # ---- Check server health ----------------------------------------------
    try:
        resp = requests.get(f"{args.server}/health", timeout=5)
        health = resp.json()
        models = health.get("models", {})
        print(f"\nServer: {health.get('status')}")
        for name, status in models.items():
            mark = "✓" if status == "ready" else "…" if status == "loading" else "✗"
            print(f"  {mark} {name}: {status}")
    except Exception as e:
        print(f"\nCannot reach server at {args.server}: {e}")
        p.terminate()
        sys.exit(1)

    # ---- Start meeting -----------------------------------------------------
    title = args.title or input("\nMeeting title (Enter to skip): ").strip() or None
    try:
        resp = requests.post(f"{args.server}/meetings/start",
                             json={"title": title}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Failed to start meeting: {e}")
        p.terminate()
        sys.exit(1)

    session_id = data["session_id"]
    meeting_id = data["meeting_id"]
    print(f"\nMeeting started")
    print(f"  Session : {session_id}")
    print(f"  Meeting : {meeting_id}\n")

    # ---- Open audio stream ------------------------------------------------
    native_rate = int(device_info["defaultSampleRate"])
    capture_rate = TARGET_RATE if supports_rate(p, device_index, TARGET_RATE) else native_rate

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=capture_rate,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK_SIZE,
    )

    print(f"Recording at {capture_rate}Hz "
          f"{'(native)' if capture_rate == TARGET_RATE else f'→ resampled to {TARGET_RATE}Hz'}  "
          f"  Ctrl+C to stop\n")

    chunk_index = 0
    running = True

    def stop(sig=None, frame=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)

    # ---- Capture loop -----------------------------------------------------
    while running:
        audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        audio = np.frombuffer(audio_data, dtype=np.int16)

        if capture_rate != TARGET_RATE:
            audio = resample(audio, capture_rate, TARGET_RATE)

        # Level meter
        if chunk_index % 10 == 0:
            rms = int(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
            filled = min(40, rms // 80)
            bar = "█" * filled + "░" * (40 - filled)
            print(f"\r  [{bar}] {rms:5d}", end="", flush=True)

        chunk = {
            "session_id": session_id,
            "chunk_index": chunk_index,
            "sample_rate": TARGET_RATE,
            "audio_data": base64.b64encode(audio.astype(np.int16).tobytes()).decode(),
        }

        try:
            requests.post(f"{args.server}/meetings/stream", json=chunk, timeout=2)
        except Exception as e:
            print(f"\nStream error (chunk {chunk_index}): {e}")

        chunk_index += 1

    # ---- Stop meeting -----------------------------------------------------
    print("\n\nStopping meeting...")
    stream.stop_stream()
    stream.close()
    p.terminate()

    try:
        resp = requests.post(
            f"{args.server}/meetings/stop",
            json={"session_id": session_id, "meeting_id": meeting_id},
            timeout=15,
        )
        print(f"Meeting saved.")
        print(f"  GET {args.server}/meetings/{meeting_id}")
        print(f"  GET {args.server}/meetings/{meeting_id}/transcripts")
        print(f"  GET {args.server}/meetings/{meeting_id}/speakers")
    except Exception as e:
        print(f"Failed to stop meeting cleanly: {e}")


if __name__ == "__main__":
    main()
