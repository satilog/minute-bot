"""Post-processing: attribute transcript chunks to identified speakers.

Problem
-------
Transcription and diarization run as independent streaming pipelines on
separate buffer windows (5s vs 30s).  Transcripts are therefore saved without
a speaker_id.  This module fixes that after the meeting ends.

Pipeline
--------
1. Identify speakers: match each speaker's stored voice embedding against global
   speaker_profiles.  Matched speakers get their profile name; unmatched ones
   are labelled "Unidentified Speaker".
2. Attribute raw transcripts (Whisper segments) to speakers by time-overlap.
3. Mark speaker_attribution_status = "completed".

LLM transcript cleanup and graph extraction are NOT part of this pipeline.
They are triggered separately via POST /meetings/<id>/process (Stage 2).

Algorithm
---------
For each unattributed row [t_start, t_end] find the diarization segment
[d_start, d_end] with the greatest time overlap:

    overlap = max(0, min(t_end, d_end) - max(t_start, d_start))

Assign speaker_id from the best-overlapping segment.  Rows with zero overlap
(e.g. they fall in a gap between diarization windows) are left unattributed.

Usage
-----
Called automatically from the /meetings/stop endpoint in a background thread.
The meeting's speaker_attribution_status column tracks progress so the UI can
show an appropriate indicator.

    UI polling:  GET /meetings/<id>  → speaker_attribution_status
    Values:      pending | processing | completed | failed
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def _best_speaker(
    t_start: float,
    t_end: float,
    segments: list[dict],
) -> Optional[str]:
    """Return the speaker_id with maximum time overlap, or None."""
    best_id: Optional[str] = None
    best_overlap = 0.0

    for seg in segments:
        overlap = max(0.0, min(t_end, seg["end_time"]) - max(t_start, seg["start_time"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_id = seg["speaker_id"]

    return best_id


def _attribute_table(rows: list[dict], segments: list[dict]) -> list[tuple[str, str]]:
    """Return (row_id, speaker_id) pairs for rows that can be matched."""
    return [
        (row["id"], speaker_id)
        for row in rows
        if (speaker_id := _best_speaker(row["start_time"], row["end_time"], segments))
    ]


_UNIDENTIFIED_LABEL = "Unidentified Speaker"


def identify_meeting_speakers(meeting_id: str, db) -> None:
    """Post-meeting speaker profile identification.

    For each speaker in the meeting that was not matched to a profile during
    the real-time diarization pass (profile_id IS NULL), attempt a second
    match using the stored voice_embedding.

    Outcomes:
        - Embedding present + profile match found → speaker_name set to profile name
        - Embedding present + no match found      → speaker_name set to "Unidentified Speaker"
        - No embedding stored                     → speaker_name set to "Unidentified Speaker"

    Speakers already linked to a profile (profile_id set in real-time) are
    left unchanged.
    """
    speakers = db.speakers.get_by_meeting(meeting_id)
    if not speakers:
        logger.info("identify_speakers: no speakers found for meeting %s", meeting_id)
        return

    matched = 0
    unidentified = 0

    for speaker in speakers:
        speaker_id = speaker["id"]
        speaker_label = speaker.get("speaker_label", "?")

        # Skip speakers already matched during real-time diarization
        if speaker.get("profile_id"):
            logger.info(
                "identify_speakers: %s already matched (profile_id=%s), skipping",
                speaker_label, speaker["profile_id"][:8],
            )
            continue

        embedding = speaker.get("voice_embedding")
        if embedding:
            try:
                matches = db.speaker_profiles.find_by_embedding(embedding, threshold=0.7)
            except Exception as e:
                logger.error("identify_speakers: profile query failed for %s: %s", speaker_label, e)
                matches = []

            if matches:
                profile = matches[0]
                db.speakers.update_profile_match(speaker_id, profile["name"], profile["id"])
                logger.info(
                    "identify_speakers: %s → %r (similarity=%.3f)",
                    speaker_label, profile["name"], profile.get("similarity", 0),
                )
                matched += 1
                continue

        # No embedding or no profile match
        db.speakers.update_profile_match(speaker_id, _UNIDENTIFIED_LABEL, None)
        logger.info("identify_speakers: %s → %s", speaker_label, _UNIDENTIFIED_LABEL)
        unidentified += 1

    logger.info(
        "identify_speakers: meeting=%s  matched=%d  unidentified=%d  skipped=%d",
        meeting_id, matched, unidentified,
        len(speakers) - matched - unidentified,
    )


def run_attribution(meeting_id: str, session_id: str) -> None:
    """Identify speakers and attribute raw transcript rows to diarized speakers.

    Pipeline:
        1. Match speaker voice embeddings against global profiles
        2. Attribute raw transcripts to speakers via diarization time-overlap
        3. Mark speaker_attribution_status = completed

    LLM transcript cleanup and graph generation are NOT run here — they are
    triggered separately when the user clicks "Process Transcript" in the UI
    (POST /meetings/<id>/process → core.graph_processing.run_graph_processing).

    Updates meeting.speaker_attribution_status throughout:
        processing → completed  (success)
        processing → failed     (unrecoverable error)
    """
    from minute_bot.api.diarization import get_and_clear_segments
    from minute_bot.db import MinuteBotDB

    db = MinuteBotDB()

    try:
        db.meetings.update_speaker_attribution_status(meeting_id, "processing")
    except Exception as e:
        logger.error("Attribution: failed to set status=processing for %s: %s", meeting_id, e)
        return

    try:
        # Step 1: identify speakers against global profiles
        identify_meeting_speakers(meeting_id, db)

        segments = get_and_clear_segments(session_id)

        if not segments:
            logger.warning(
                "Attribution: no diarization segments for session %s — "
                "transcripts will remain unattributed.",
                session_id,
            )
        else:
            # Step 2: attribute raw transcripts to speakers via time-overlap matching
            raw_rows = db.transcripts.get_unattributed_by_meeting(meeting_id)
            raw_assignments = _attribute_table(raw_rows, segments)
            if raw_assignments:
                db.transcripts.update_speaker_batch(raw_assignments)

            logger.info(
                "Attribution: meeting=%s  raw=%d/%d attributed",
                meeting_id,
                len(raw_assignments), len(raw_rows),
            )

        db.meetings.update_speaker_attribution_status(meeting_id, "completed")

    except Exception as e:
        logger.error("Attribution: failed for meeting %s: %s", meeting_id, e)
        try:
            db.meetings.update_speaker_attribution_status(meeting_id, "failed")
        except Exception:
            pass


def run_attribution_async(meeting_id: str, session_id: str) -> None:
    """Spawn a daemon thread to run attribution without blocking the HTTP response."""
    thread = threading.Thread(
        target=run_attribution,
        args=(meeting_id, session_id),
        daemon=True,
        name=f"attribution-{meeting_id[:8]}",
    )
    thread.start()
