"""Agent: transcript_cleanup

Reflows raw Whisper transcript segments from a multi-speaker meeting recording
into clean, complete sentences with corrected punctuation and casing.

Input contract
--------------
A JSON array of segment objects.  Each segment MUST have:
    text        str    Raw transcribed text from Whisper
    start_time  float  Segment start (seconds from meeting start)
    end_time    float  Segment end   (seconds from meeting start)

Each segment MAY have:
    speaker_label  str   e.g. "SPEAKER_00".  Present only when real-time
                         diarization has been correlated with the segment.
                         Omit the key entirely when unknown.

A `remainder` string (possibly empty) is also passed — text from the previous
flush that could not form a complete sentence yet.  It is prepended to the first
segment before processing.

Output contract
---------------
Valid JSON, no markdown fences, no explanation text:
{
  "sentences": [
    {
      "text":          "Complete, clean sentence.",
      "start_time":    0.0,
      "end_time":      4.8,
      "speaker_label": "SPEAKER_00"   // only present if known
    }
  ],
  "remainder": "incomplete trailing text or empty string"
}

Design notes
------------
- This agent is invoked every ~30 s of accumulated audio, so each batch may
  contain speech from MULTIPLE speakers.
- Speaker boundaries must NEVER be merged across different speaker_labels.
- When speaker_label is absent for a segment, do not infer or invent one.
- The remainder must never carry a speaker_label; it belongs to the next batch
  where it will be re-attributed.
"""

import json
import logging
from typing import Optional

from minute_bot.config import get_settings
from minute_bot.llm.client import get_client

logger = logging.getLogger(__name__)

# ── Agent configuration ───────────────────────────────────────────────────────

AGENT_MODEL: Optional[str] = None       # None → use global llm_model from settings
AGENT_MAX_TOKENS: int = 4096

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a professional meeting transcript editor.

You receive a JSON array of raw speech-to-text segments captured from a \
multi-participant meeting recording. Each segment has a text snippet produced \
by automatic speech recognition (Whisper), with start and end timestamps \
(seconds from the start of the meeting), and optionally a speaker_label \
(e.g. "SPEAKER_00") when the speaker has been identified by the diarization \
system.

Your task is to clean and reflow these segments into grammatically complete, \
readable sentences according to the rules below.

## Cleaning rules

1. Fix transcription artefacts:
   - Capitalise the first word of every sentence.
   - Add correct end punctuation (period, question mark, or exclamation mark).
   - Remove filler words (um, uh, like, you know, kind of, sort of) UNLESS \
     they appear intentional or change meaning.
   - Correct obvious ASR errors only when you are highly confident \
     (e.g. "their" vs "there").  Never alter technical terms, names, \
     or domain-specific jargon.

2. Sentence grouping:
   - Merge consecutive segments into a single sentence when they form one \
     complete thought.
   - A sentence is complete when it has a natural end: a clause boundary, \
     a full stop, a question, or a clear pause implied by the next segment \
     starting a new thought.

3. Multi-speaker handling (CRITICAL):
   - NEVER merge segments from different speaker_labels into the same sentence, \
     even if the text would grammatically flow together.
   - Each output sentence must belong to exactly one speaker.
   - If a segment has no speaker_label, treat it as a separate speaker from \
     any labelled speaker; do not assign a label to it.
   - Adjacent unlabelled segments may be merged with each other if they form \
     one sentence.

4. Timestamps:
   - start_time of a sentence = start_time of its first contributing segment.
   - end_time   of a sentence = end_time   of its last  contributing segment.

5. Remainder:
   - If the last sentence in the batch is incomplete (ends mid-thought or \
     mid-clause), do NOT include it in "sentences".
   - Place its raw text (as-is, without cleaning) in the "remainder" field so \
     it can be prepended to the next batch.
   - If all sentences are complete, set "remainder" to an empty string "".

6. Do not add, invent, or remove meaningful content beyond cleaning.

## Output format

Respond ONLY with valid JSON — no markdown fences, no explanation, no prefix text.

{
  "sentences": [
    {
      "text":          "A complete, cleaned sentence.",
      "start_time":    0.0,
      "end_time":      4.8,
      "speaker_label": "SPEAKER_00"
    },
    {
      "text":       "Another sentence with no known speaker.",
      "start_time": 5.1,
      "end_time":   9.3
    }
  ],
  "remainder": "any incomplete trailing text or empty string"
}

Notes:
- Include "speaker_label" in a sentence only if ALL contributing segments \
  carry the same non-null speaker_label.
- Omit "speaker_label" entirely (do not set it to null) when unknown.
"""


# ── Agent entry point ─────────────────────────────────────────────────────────

def run(
    segments: list[dict],
    remainder: str = "",
) -> tuple[list[dict], str]:
    """Reflow raw Whisper segments into clean, complete sentences.

    Args:
        segments:  Raw Whisper segments — each must have {text, start_time,
                   end_time} and optionally {speaker_label}.
        remainder: Incomplete sentence text carried over from the previous
                   batch.  Prepended to the first segment's text before
                   sending to the LLM.

    Returns:
        (sentences, new_remainder)
        sentences     — list of {text, start_time, end_time[, speaker_label]}
        new_remainder — incomplete trailing text to prepend to the next batch
    """
    if not segments:
        return [], remainder

    settings = get_settings()

    # Prepend carried-over remainder text to the first segment
    batch = [s.copy() for s in segments]
    if remainder:
        batch[0] = {**batch[0], "text": remainder + " " + batch[0]["text"]}

    model = AGENT_MODEL or settings.llm_model
    user_message = json.dumps(batch, ensure_ascii=False)

    logger.info(
        "[transcript_cleanup] calling LLM (model=%s, segments=%d, remainder_len=%d)",
        model, len(batch), len(remainder),
    )

    # Let RuntimeError (e.g. missing ANTHROPIC_API_KEY) propagate — callers
    # must handle it so processing is marked failed rather than silently empty.
    client = get_client()

    response = client.messages.create(
        model=model,
        max_tokens=AGENT_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    logger.info("[transcript_cleanup] raw response (first 500 chars): %r", raw[:500])

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"[transcript_cleanup] LLM returned invalid JSON: {e}\n"
            f"Raw response (first 500 chars): {raw[:500]!r}"
        ) from e

    sentences = parsed.get("sentences", [])
    new_remainder = parsed.get("remainder", "")

    # Validate required fields; drop malformed entries
    valid = [
        s for s in sentences
        if isinstance(s.get("text"), str)
        and isinstance(s.get("start_time"), (int, float))
        and isinstance(s.get("end_time"), (int, float))
    ]

    # Ensure speaker_label is only kept when it is a non-empty string
    for s in valid:
        label = s.get("speaker_label")
        if not isinstance(label, str) or not label.strip():
            s.pop("speaker_label", None)

    logger.info(
        "[transcript_cleanup] %d segments → %d sentences (remainder=%d chars)",
        len(segments), len(valid), len(new_remainder),
    )

    return valid, new_remainder
