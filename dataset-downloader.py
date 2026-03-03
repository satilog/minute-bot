"""
AMI Corpus Downloader - ES Scenario Meetings (Product Design)
=============================================================
Downloads individual headset mic (IHM) audio + manual annotations
for all ES (Elicited Scenario) product design meetings.

Audio URL pattern:
  https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/{meeting_id}/audio/{meeting_id}.Headset-{n}.wav

Each meeting has 4 speakers (Headset-0, Headset-1, Headset-2, Headset-3).
Each session (e.g. ES2002) has 4 meetings: a, b, c, d.

Usage:
    python download_ami_es.py --output_dir ./ami_es_data
    python download_ami_es.py --output_dir ./ami_es_data --split train
    python download_ami_es.py --output_dir ./ami_es_data --sessions ES2002 ES2003
"""

import argparse
import os
import urllib.request
from pathlib import Path

# ── ES scenario session IDs (all product design meetings) ───────────────────
# Standard train/val/test split used across the literature
ES_TRAIN = [
    "ES2002", "ES2005", "ES2006", "ES2007", "ES2008",
    "ES2009", "ES2010", "ES2012", "ES2013", "ES2015", "ES2016",
]
ES_VAL  = ["ES2003", "ES2011"]
ES_TEST = ["ES2004", "ES2014"]

ALL_ES_SESSIONS = ES_TRAIN + ES_VAL + ES_TEST  # 15 sessions × 4 meetings = 60 meetings

# Each session has 4 meetings (a, b, c, d) and each meeting has 4 headset mics (0-3)
MEETING_SUFFIXES = ["a", "b", "c", "d"]
HEADSET_INDICES  = [0, 1, 2, 3]

BASE_URL       = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
ANNOTATION_URL = "http://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"


def expand_sessions(sessions):
    """Expand session IDs like ['ES2002'] into meeting IDs like ['ES2002a', 'ES2002b', ...]."""
    return [s + suffix for s in sessions for suffix in MEETING_SUFFIXES]


def download_file(url, dest_path, label=""):
    """Download a file with a simple progress indicator. Skips if already exists."""
    if dest_path.exists():
        print(f"  [skip]  {dest_path.name} already exists")
        return

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [down]  {label or dest_path.name}")

    try:
        def reporthook(count, block_size, total_size):
            if total_size > 0:
                pct = min(int(count * block_size * 100 / total_size), 100)
                print(f"\r         {pct}%", end="", flush=True)

        urllib.request.urlretrieve(url, dest_path, reporthook=reporthook)
        print()  # newline after progress
    except Exception as e:
        print(f"\n  [ERROR] Failed to download {url}: {e}")
        if dest_path.exists():
            dest_path.unlink()  # remove partial file


def download_annotations(output_dir):
    """Download the manual annotations zip (transcripts, dialogue acts, summaries)."""
    zip_path = output_dir / "ami_public_manual_1.6.2.zip"
    print("\n── Downloading annotations ──────────────────────────────────")
    download_file(ANNOTATION_URL, zip_path, label="ami_public_manual_1.6.2.zip")

    # Unzip if not already done
    extract_dir = output_dir / "ami_public_manual_1.6.2"
    if not extract_dir.exists():
        print("  [unzip] Extracting annotations...")
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(output_dir)
        print(f"  [done]  Extracted to {extract_dir}")
    else:
        print(f"  [skip]  Annotations already extracted at {extract_dir}")


def download_audio(meeting_ids, output_dir):
    """Download IHM headset audio for the given list of meeting IDs."""
    total = len(meeting_ids) * len(HEADSET_INDICES)
    done  = 0

    print(f"\n── Downloading audio ({len(meeting_ids)} meetings × 4 headsets = {total} files) ──")

    for meeting_id in meeting_ids:
        print(f"\n  Session: {meeting_id}")
        audio_dir = output_dir / "audio" / meeting_id
        audio_dir.mkdir(parents=True, exist_ok=True)

        for n in HEADSET_INDICES:
            filename = f"{meeting_id}.Headset-{n}.wav"
            url      = f"{BASE_URL}/{meeting_id}/audio/{filename}"
            dest     = audio_dir / filename
            download_file(url, dest, label=filename)
            done += 1

    print(f"\n── Audio download complete: {done}/{total} files ────────────")


def main():
    parser = argparse.ArgumentParser(
        description="Download AMI ES scenario meetings (IHM audio + annotations)"
    )
    parser.add_argument(
        "--output_dir", type=str, default="./ami_es_data",
        help="Root directory to save downloaded files (default: ./ami_es_data)"
    )
    parser.add_argument(
        "--split", type=str, choices=["train", "val", "test", "all"], default="all",
        help="Which split to download: train, val, test, or all (default: all)"
    )
    parser.add_argument(
        "--sessions", nargs="+", default=None,
        help="Optional: download specific sessions only, e.g. --sessions ES2002 ES2003"
    )
    parser.add_argument(
        "--no_annotations", action="store_true",
        help="Skip downloading annotations (audio only)"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which sessions to download
    if args.sessions:
        # Validate session names
        invalid = [s for s in args.sessions if s not in ALL_ES_SESSIONS]
        if invalid:
            print(f"Warning: unknown sessions {invalid}. Valid ES sessions are:\n  {ALL_ES_SESSIONS}")
        sessions = [s for s in args.sessions if s in ALL_ES_SESSIONS]
    elif args.split == "train":
        sessions = ES_TRAIN
    elif args.split == "val":
        sessions = ES_VAL
    elif args.split == "test":
        sessions = ES_TEST
    else:
        sessions = ALL_ES_SESSIONS

    meeting_ids = expand_sessions(sessions)

    print(f"\nAMI ES Corpus Downloader")
    print(f"  Split:       {args.split}")
    print(f"  Sessions:    {sessions}")
    print(f"  Meetings:    {len(meeting_ids)}  ({meeting_ids[0]} … {meeting_ids[-1]})")
    print(f"  Output dir:  {output_dir.resolve()}")

    # Download annotations (shared across all meetings)
    if not args.no_annotations:
        download_annotations(output_dir)

    # Download audio
    download_audio(meeting_ids, output_dir)

    print("\n✓ All done.")
    print(f"  Annotations : {output_dir / 'ami_public_manual_1.6.2'}")
    print(f"  Audio       : {output_dir / 'audio'}")


if __name__ == "__main__":
    main()