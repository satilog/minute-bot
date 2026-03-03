"""Agent: graph_generation

Extracts a structured knowledge graph (events, entities, relationships) from
the processed transcripts of a completed meeting.

Input contract
--------------
A JSON array of processed-transcript objects.  Each object MUST have:
    text          str    A clean, complete sentence from the meeting
    start_time    float  Sentence start (seconds from meeting start)
    end_time      float  Sentence end

Each object MAY have:
    speaker_name  str    Resolved display name (e.g. "Alice") or
                         "Unidentified Speaker" if not matched

Output contract
---------------
Valid JSON, no markdown fences, no explanation text:
{
  "events": [
    {
      "event_type":   "decision",
      "description":  "We will migrate to PostgreSQL by end of quarter.",
      "timestamp":    45.0
    }
  ],
  "entities": [
    {"entity_type": "person",   "entity_name": "Alice"},
    {"entity_type": "tool",     "entity_name": "PostgreSQL"}
  ],
  "relationships": [
    {
      "source_entity": "Alice",
      "target_entity": "PostgreSQL",
      "relationship_type": "refers_to"
    }
  ]
}

Valid event_type values (snake_case):
    action_item, decision, task_assignment, task_reassignment,
    task_cancellation, question, answer, proposal, agreement,
    disagreement, issue, resolution, status_update, deadline,
    priority_change, dependency, command

Valid entity_type values (snake_case):
    person, speaker, assignee, owner, reviewer, stakeholder,
    document, presentation, spreadsheet, ticket, code_repository,
    url, dataset, tool, organization

Valid relationship_type values:
    said_by, assigned_to, refers_to, depends_on, blocks, resolves,
    overrides, follows_from, contradicts, supports, happens_at,
    part_of, discussed_in
"""

import json
import logging
from typing import Optional

from minute_bot.config import get_settings
from minute_bot.llm.client import get_client

logger = logging.getLogger(__name__)

# ── Agent configuration ───────────────────────────────────────────────────────

AGENT_MODEL: Optional[str] = None       # None → use global llm_model from settings
AGENT_MAX_TOKENS: int = 8192

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a knowledge-graph extraction engine for meeting transcripts.

You receive a JSON array of processed meeting sentences.  Each sentence has a
text field, optional speaker_name, and timestamp fields.

Your task is to extract three types of structured knowledge:

## 1. Events
Identify meaningful semantic events that occurred in the meeting.

Classify each event using one of these types:
  action_item      — A concrete task someone agreed to do
  decision         — A conclusion the group reached
  task_assignment  — An explicit delegation ("Alice, please handle X")
  task_reassignment — Reassigning a task from one person to another
  task_cancellation — Cancelling a previously assigned task
  question         — An open question raised
  answer           — A direct answer to a question
  proposal         — A suggestion or idea put forward
  agreement        — Participants explicitly agreed on something
  disagreement     — Explicit pushback or disagreement
  issue            — A problem, blocker, or risk raised
  resolution       — A previously raised issue was resolved
  status_update    — A progress report on an existing piece of work
  deadline         — A date or time constraint was established
  priority_change  — The priority of something changed
  dependency       — One item depends on another
  command          — A directive or request from one participant to another

Each event needs:
  event_type    (snake_case from the list above)
  description   (1–2 clear sentences capturing what was said)
  timestamp     (start_time of the sentence where this event was detected)

## 2. Entities
Extract named things that are referenced in the conversation.  Only include
entities that are clearly mentioned, not inferred.

Entity types:
  person, speaker, assignee, owner, reviewer, stakeholder — people roles
  document, presentation, spreadsheet, ticket, code_repository,
  url, dataset, tool, organization — artifacts

Each entity needs:
  entity_type  (snake_case from the list above)
  entity_name  (the name as it appears in the transcript)

De-duplicate: if the same person or thing is mentioned multiple times, include
it only once.

## 3. Relationships
Describe meaningful connections between entities.  Use entity names exactly as
you listed them in the entities array.

Relationship types:
  said_by        — an event or statement was made by a person
  assigned_to    — a task is assigned to a person
  refers_to      — an entity references another entity
  depends_on     — one item depends on another
  blocks         — one item blocks another
  resolves       — an action resolves an issue
  overrides      — a decision overrides a previous one
  follows_from   — one item logically follows from another
  contradicts    — two items are in contradiction
  supports       — one item supports another
  happens_at     — an event is associated with a time/deadline
  part_of        — one entity is part of a larger entity
  discussed_in   — an entity was discussed in the context of a meeting event

Only include relationships that are clearly supported by the transcript.

## Output format

Respond ONLY with valid JSON.  No markdown fences, no explanation text.

{
  "events": [
    {"event_type": "...", "description": "...", "timestamp": 0.0}
  ],
  "entities": [
    {"entity_type": "...", "entity_name": "..."}
  ],
  "relationships": [
    {"source_entity": "...", "target_entity": "...", "relationship_type": "..."}
  ]
}

If the transcript contains no meaningful events, entities, or relationships,
return empty arrays.  Never invent content not present in the transcript.
"""


# ── Agent entry point ─────────────────────────────────────────────────────────

def run(transcripts: list[dict]) -> dict:
    """Extract events, entities, and relationships from processed transcripts.

    Args:
        transcripts: List of processed-transcript rows — each must have
                     {text, start_time, end_time} and optionally {speaker_name}.

    Returns:
        dict with keys 'events', 'entities', 'relationships' (each a list).
        Returns empty dict on failure so callers can proceed gracefully.
    """
    if not transcripts:
        return {"events": [], "entities": [], "relationships": []}

    settings = get_settings()

    # Build input: strip DB-internal fields, keep only what the LLM needs
    input_rows = []
    for t in transcripts:
        row: dict = {
            "text": t.get("text", ""),
            "start_time": t.get("start_time", 0.0),
            "end_time": t.get("end_time", 0.0),
        }
        speaker_name = t.get("speaker_name")
        if speaker_name and speaker_name != "Unidentified Speaker":
            row["speaker_name"] = speaker_name
        input_rows.append(row)

    model = AGENT_MODEL or settings.llm_model
    user_message = json.dumps(input_rows, ensure_ascii=False)

    try:
        client = get_client()
        response = client.messages.create(
            model=model,
            max_tokens=AGENT_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[graph_generation] LLM returned invalid JSON: %s", e)
        return {"events": [], "entities": [], "relationships": []}
    except Exception as e:
        logger.error("[graph_generation] LLM call failed: %s", e)
        return {"events": [], "entities": [], "relationships": []}

    events = [
        e for e in parsed.get("events", [])
        if isinstance(e.get("event_type"), str) and isinstance(e.get("description"), str)
    ]
    entities = [
        e for e in parsed.get("entities", [])
        if isinstance(e.get("entity_type"), str) and isinstance(e.get("entity_name"), str)
    ]
    relationships = [
        r for r in parsed.get("relationships", [])
        if isinstance(r.get("source_entity"), str)
        and isinstance(r.get("target_entity"), str)
        and isinstance(r.get("relationship_type"), str)
    ]

    logger.info(
        "[graph_generation] extracted  events=%d  entities=%d  relationships=%d",
        len(events), len(entities), len(relationships),
    )

    return {"events": events, "entities": entities, "relationships": relationships}
