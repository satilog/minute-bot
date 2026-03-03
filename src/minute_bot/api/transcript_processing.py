"""Post-meeting LLM transcript processing.

Runs after a meeting stops (triggered from speaker_attribution.run_attribution)
once all raw transcripts have been attributed to speakers.

Pipeline position:
    [speaker_attribution] -> speaker_id written to transcripts
                                      |
                          [transcript_processing]  <- this module
                                      |
                          processed_transcripts table  (clean sentences,
                                                         speaker_id already set)

Why post-meeting (not real-time):
    During recording Whisper segments have no speaker information -- diarization
    runs on a different 30-second window and the two pipelines are not correlated
    in real-time.  Running LLM cleanup post-meeting means:
      1. All speaker_ids are already attributed on raw transcripts.
      2. The LLM receives speaker_label for every segment, so it never merges
         speech from different speakers into the same sentence.
      3. No LLM latency is added to the live recording path.

Batching:
    Raw transcripts are sorted by start_time and processed in 60-second windows.
    Any incomplete trailing sentence (the "remainder") is carried forward and
    prepended to the next batch so sentence boundaries are always clean.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Approximate audio window sent to the LLM per batch (seconds).
_BATCH_SECONDS = 60.0


def process_meeting_transcripts(meeting_id: str) -> None:
    """Reflow all raw transcripts for a completed meeting into clean sentences.

    Reads attributed raw transcripts (speaker_id already set by attribution),
    sends them to the transcript_cleanup LLM agent in 60-second time batches,
    and writes the resulting clean sentences to processed_transcripts -- each
    row inherits the speaker_id of its contributing segments.

    Args:
        meeting_id: UUID of the completed meeting.
    """
    from minute_bot.agents.transcript_cleanup import run as cleanup_segments
    from minute_bot.db import MinuteBotDB

    db = MinuteBotDB()

    # Build speaker_label -> speaker_id lookup
    speakers = db.speakers.get_by_meeting(meeting_id)
    label_to_id: dict[str, str] = {
        s["speaker_label"]: s["id"] for s in speakers if s.get("speaker_label")
    }

    # Fetch raw transcripts with joined speaker info.
    # Each row: id, meeting_id, text, start_time, end_time, speaker_id,
    #           speakers: {speaker_label, speaker_name}
    raw = db.transcripts.get_by_meeting(meeting_id)
    if not raw:
        logger.info("transcript_processing: no raw transcripts for meeting %s", meeting_id)
        return

    logger.info(
        "transcript_processing: processing %d raw segments for meeting %s",
        len(raw), meeting_id,
    )

    # Build LLM-input segments with speaker_label preserved alongside speaker_id
    annotated: list[tuple[Optional[str], dict]] = []
    for t in raw:
        seg: dict = {
            "text": t["text"],
            "start_time": t["start_time"],
            "end_time": t["end_time"],
        }
        speaker_info = t.get("speakers") or {}
        label = speaker_info.get("speaker_label") if isinstance(speaker_info, dict) else None
        if label:
            seg["speaker_label"] = label
        annotated.append((t.get("speaker_id"), seg))

    # Process in 60-second time windows
    all_rows: list[dict] = []
    remainder = ""
    i = 0

    while i < len(annotated):
        batch_start_time = annotated[i][1]["start_time"]
        batch_speaker_ids: list[Optional[str]] = []
        batch_segs: list[dict] = []

        while i < len(annotated):
            sid, seg = annotated[i]
            if seg["start_time"] - batch_start_time >= _BATCH_SECONDS:
                break
            batch_segs.append(seg)
            batch_speaker_ids.append(sid)
            i += 1

        if not batch_segs:
            i += 1
            continue

        try:
            sentences, remainder = cleanup_segments(batch_segs, remainder=remainder)
        except Exception as e:
            logger.error(
                "transcript_processing: LLM batch failed for meeting %s: %s",
                meeting_id, e,
            )
            continue

        for sentence in sentences:
            # Resolve speaker_id: prefer label->id map if LLM preserved speaker_label,
            # otherwise fall back to the first batch segment's speaker_id.
            label = sentence.get("speaker_label")
            speaker_id: Optional[str] = (
                label_to_id.get(label)
                if label
                else (batch_speaker_ids[0] if batch_speaker_ids else None)
            )
            all_rows.append(
                {
                    "meeting_id": meeting_id,
                    "speaker_id": speaker_id,
                    "text": sentence["text"],
                    "start_time": sentence["start_time"],
                    "end_time": sentence["end_time"],
                }
            )

    # Flush any incomplete trailing remainder as a final row
    if remainder.strip() and annotated:
        last_speaker_id, last_seg = annotated[-1]
        all_rows.append(
            {
                "meeting_id": meeting_id,
                "speaker_id": last_speaker_id,
                "text": remainder.strip(),
                "start_time": last_seg["start_time"],
                "end_time": last_seg["end_time"],
            }
        )

    if not all_rows:
        logger.warning(
            "transcript_processing: LLM produced no sentences for meeting %s", meeting_id
        )
        return

    try:
        db.processed_transcripts.create_batch(all_rows)
        logger.info(
            "transcript_processing: saved %d processed sentences for meeting %s",
            len(all_rows), meeting_id,
        )
    except Exception as e:
        logger.error(
            "transcript_processing: DB write failed for meeting %s: %s",
            meeting_id, e,
        )
