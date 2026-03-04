# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Minute Bot is an agentic meeting memory system that transforms unstructured meeting audio into structured, speaker-aware, temporally interpretable knowledge graphs. The system processes meeting audio to identify speakers, transcribe speech, extract semantic events and entities, and build a queryable memory graph backed by a vector-indexed triplet store.

## Architecture

The system has two parts: a server (Docker / Python package) and a thin host-side client script.

```
┌────────────────────────────────────────────────────────────────┐
│  client.py (host)                                              │
│  Captures mic audio → streams chunks to server via HTTP        │
│  --enroll "Name" → enrolls a voice profile                     │
└─────────────────────────┬──────────────────────────────────────┘
                          │ POST /meetings/stream
                          ▼
┌────────────────────────────────────────────────────────────────┐
│                      Minute Bot API (server)                    │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Meetings   │  │ Transcription│  │     Diarization      │  │
│  │  /start     │  │  /status     │  │     /status          │  │
│  │  /stream    │  └──────────────┘  └──────────────────────┘  │
│  │  /stop      │                                               │
│  │  /process   │  ← manual graph processing trigger            │
│  │  /reprocess │  ← manual speaker re-attribution              │
│  └─────────────┘                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Profiles   │  │    Events    │  │       Agent          │  │
│  │  /enroll    │  │  /stream SSE │  │     /query           │  │
│  │  GET/DELETE │  └──────────────┘  └──────────────────────┘  │
│  └─────────────┘                                               │
│                          │                                     │
│                          ▼                                     │
│                 ┌─────────────────┐                            │
│                 │  Redis Pub/Sub  │  4 channels:               │
│                 │  audio:chunks   │  transcription:segments    │
│                 │  diarization:   │  graph:events              │
│                 │  segments       │                            │
│                 └─────────────────┘                            │
│                          │                                     │
│    ┌────────────────────┬┴─────────────────┐                  │
│    ▼                    ▼                  ▼                  │
│ ┌──────────┐    ┌──────────────┐    ┌──────────────┐         │
│ │ Supabase │    │   Whisper    │    │   Pyannote   │         │
│ │ Storage  │    │   (STT)      │    │ (Diarization)│         │
│ └──────────┘    └──────────────┘    └──────────────┘         │
│                                                               │
│  Post-meeting (background threads):                           │
│  Stage 1 (auto):  speaker_attribution → raw transcripts       │
│  Stage 2 (manual): memory_graph.processing →                  │
│                    processed_transcripts + knowledge graph     │
└────────────────────────────────────────────────────────────────┘
```

All services (Whisper, Pyannote, Redis pub/sub) are initialized automatically at server startup via `ServiceRegistry` in `services.py`. There are no manual `/start` or `/stop` endpoints for individual services.

## Project Structure

```
minute-bot/
├── pyproject.toml              # Python package definition
├── docker-compose.yml          # Container orchestration
├── Dockerfile                  # Application container
├── client.py                   # Host-side audio capture script
├── requirements-client.txt     # Client dependencies (pyaudio, numpy, requests)
│
├── src/minute_bot/
│   ├── api/                    # Flask REST endpoints
│   │   ├── __init__.py         # create_app — registers all blueprints, starts pipelines
│   │   ├── health.py           # GET /health — server + model status
│   │   ├── streaming.py        # Audio pipeline helpers, GET /streaming/devices
│   │   ├── transcription.py    # GET /transcription/status + pipeline init
│   │   ├── diarization.py      # GET /diarization/status + pipeline init
│   │   ├── profiles.py         # Speaker profile enrollment/management
│   │   ├── meetings.py         # Primary workflow: start/stream/stop + all data queries
│   │   ├── events.py           # GET /events/stream — Server-Sent Events
│   │   ├── agent.py            # POST /agent/query — NL Q&A over meeting data
│   │   └── transcript_processing.py  # LLM cleanup helper (called from memory_graph)
│   │
│   ├── core/                   # Core processing logic
│   │   ├── audio_capture.py    # PyAudio microphone capture (server-side, unused in prod)
│   │   ├── audio_buffer.py     # Audio chunk accumulation per session
│   │   ├── transcriber.py      # Whisper (faster-whisper) transcription
│   │   ├── diarizer.py         # Pyannote diarization + voice embedding extraction
│   │   └── speaker_attribution.py  # Post-meeting: match transcripts to speakers
│   │
│   ├── audio/                  # Audio utilities
│   │   ├── encoding.py         # Base64 encode/decode
│   │   ├── processing.py       # Resample, normalize
│   │   └── analysis.py         # Silence detection, RMS
│   │
│   ├── db/                     # Database layer — one file per table
│   │   ├── client.py           # Supabase client init
│   │   ├── meetings.py         # MeetingsDB
│   │   ├── audio_files.py      # AudioFilesDB + Storage
│   │   ├── transcripts.py      # TranscriptsDB (raw Whisper segments)
│   │   ├── processed_transcripts.py  # ProcessedTranscriptsDB (LLM-cleaned sentences)
│   │   ├── speakers.py         # SpeakersDB (per-meeting, pgvector 512-dim)
│   │   ├── speaker_profiles.py # SpeakerProfilesDB (global, pgvector 512-dim)
│   │   ├── events.py           # EventsDB (semantic meeting events)
│   │   ├── entities.py         # EntitiesDB (people, artifacts)
│   │   ├── relationships.py    # RelationshipsDB (entity connections)
│   │   ├── triplets.py         # TripletsDB (subject-predicate-object + 1536-dim embeddings)
│   │   ├── triplet_links.py    # TripletLinksDB (directed edges between triplets)
│   │   ├── triplet_storage.py  # TripletStorageDB (meeting-audio + meeting-transcripts buckets)
│   │   └── __init__.py         # MinuteBotDB — unified client, wires all tables
│   │
│   ├── memory_graph/           # Knowledge graph module — single public interface
│   │   ├── __init__.py         # MemoryGraph class + process_meeting_async()
│   │   ├── extraction.py       # LLM agent: events/entities/relationships from transcripts
│   │   └── processing.py       # Pipeline orchestrator: transcript cleanup → graph extraction
│   │
│   ├── agents/                 # LLM agents (one file per agent)
│   │   ├── __init__.py
│   │   └── transcript_cleanup.py  # Reflows raw Whisper segments into clean sentences
│   │
│   ├── models/                 # Pydantic models (by domain)
│   │   ├── audio.py            # AudioChunk, AudioSegment
│   │   ├── transcription.py    # TranscriptionWord, TranscriptionSegment
│   │   ├── speaker.py          # SpeakerSegment, SpeakerProfile
│   │   ├── events.py           # EventType, MeetingEvent
│   │   ├── entities.py         # Entity, Relationship, enums
│   │   ├── session.py          # MeetingSession, ProcessingStatus
│   │   └── records.py          # Database record models
│   │
│   ├── pubsub/                 # Redis pub/sub
│   │   ├── client.py           # Redis connection
│   │   ├── publisher.py        # Publish transcript/diarization events
│   │   ├── subscriber.py       # Subscribe and dispatch
│   │   └── graph_publisher.py  # Publish graph events (entity/relationship/event/speaker)
│   │
│   ├── services.py             # ServiceRegistry: eager ML model init at startup
│   └── config.py               # Centralized configuration (pydantic-settings)
│
├── supabase/
│   └── migrations/             # SQL migrations — apply in order via Supabase SQL Editor
│       ├── 001_initial_schema.sql          # Core tables + pgvector + RPCs
│       ├── 002_speaker_profiles.sql        # Global speaker profiles table
│       ├── 003_vector_512.sql              # Resize speaker embedding vectors to 512-dim
│       ├── 003_graph_processing_status.sql # Add graph_processing_status to meetings
│       ├── 004_speaker_attribution_status.sql  # Add speaker_attribution_status to meetings
│       ├── 005_speakers_profile_fk.sql     # FK: speakers.profile_id → speaker_profiles.id
│       ├── 006_processed_transcripts.sql   # processed_transcripts table
│       └── 007_triplet_schema.sql          # triplets + triplet_links + HNSW index + 4 RPCs
│
└── tests/                      # Test suite
```

> **Note on migration naming**: Two files share the `003_` prefix. Apply `003_vector_512.sql` before `003_graph_processing_status.sql`. Both are idempotent.

## Build & Run

```bash
# Install locally for development
pip install -e .

# Run the application
minute-bot
# or
python -m minute_bot.api

# Run with Docker
docker-compose up --build

# Run the client (host machine — separate venv)
python3 -m venv .venv-client
.venv-client/bin/pip install -r requirements-client.txt
python client.py                        # start a meeting (auto-detects HyperX mic)
python client.py --enroll "Alice"       # enroll a speaker profile
python client.py --list-devices         # show available microphones
python client.py --device 2             # use a specific device by index
python client.py --title "Standup"      # set meeting title upfront
```

## Key Technologies

- **Speech-to-Text**: faster-whisper (CTranslate2 backend)
- **Speaker Diarization**: Pyannote
- **LLM**: Anthropic Claude (transcript cleanup + graph extraction)
- **Relational Database**: Supabase (PostgreSQL with pgvector)
- **File Storage**: Supabase Storage (3 buckets: recordings, meeting-audio, meeting-transcripts)
- **Message Broker**: Redis pub/sub (4 channels)
- **Web Framework**: APIFlask (Flask + OpenAPI)

## API Endpoints

### Primary Workflow

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings/start` | POST | Create meeting → `{session_id, meeting_id}` |
| `/meetings/stream` | POST | Receive audio chunk `{session_id, audio_data, ...}` |
| `/meetings/stop` | POST | End meeting, save audio, trigger speaker attribution |
| `/meetings/status` | GET | List active recording sessions |

### Meeting Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings` | GET | List recent meetings (`?limit=10`) |
| `/meetings/<id>` | GET | Full meeting summary (all related data) |
| `/meetings/<id>/transcripts` | GET | Raw Whisper transcript segments |
| `/meetings/<id>/processed-transcripts` | GET | LLM-cleaned sentence chunks |
| `/meetings/<id>/speakers` | GET | Speakers for a meeting |
| `/meetings/<id>/speakers/<sid>/name` | PUT | Update speaker display name |
| `/meetings/<id>/events` | GET | Semantic events (`?type=` filter) |
| `/meetings/<id>/action-items` | GET | Action-item events only |
| `/meetings/<id>/entities` | GET | Extracted entities (`?type=` filter) |
| `/meetings/<id>/relationships` | GET | Entity relationships (for graph view) |
| `/meetings/<id>/audio` | GET | Audio files with signed download URLs |

### Post-Meeting Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings/<id>/process` | POST | Trigger LLM cleanup + graph extraction (Stage 2) |
| `/meetings/<id>/reprocess` | POST | Re-run speaker attribution for a completed meeting |

### Speaker Profiles

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/profiles` | GET | List all enrolled speaker profiles |
| `/profiles/enroll` | POST | Enroll voice sample `{name, audio_data}` → 201 |
| `/profiles/<id>` | DELETE | Remove a speaker profile |

### Real-time & Agent

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events/stream` | GET | SSE stream `?session_id=<id>` — transcripts, speakers, graph events |
| `/agent/query` | POST | NL Q&A `{query, session_id, meeting_id}` → `{answer, sources, node}` |

### Diagnostics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + model load status |
| `/streaming/devices` | GET | List server-side audio devices |
| `/transcription/status` | GET | Transcription pipeline state |
| `/diarization/status` | GET | Diarization pipeline state |

## Post-Meeting Processing Pipeline

Processing happens in two explicit stages after a meeting stops.

### Stage 1 — Speaker Attribution (automatic)

Triggered immediately by `/meetings/stop` in a background thread.

```
Status field: meetings.speaker_attribution_status
Values:       null/pending → processing → completed | failed
```

Steps:
1. Match each per-meeting speaker embedding against global `speaker_profiles` (cosine similarity ≥ 0.7)
2. Attribute raw transcript rows to speakers by maximum time-overlap with diarization segments
3. Run LLM transcript cleanup (`agents/transcript_cleanup`) → write `processed_transcripts`

### Stage 2 — Graph Extraction (manual, user-triggered)

Triggered by `POST /meetings/<id>/process` (the "Process Transcript" button in the UI).

```
Status field: meetings.graph_processing_status
Values:       null/pending → processing_transcripts → processing_graph → completed | failed
```

Steps:
1. LLM transcript cleanup → `processed_transcripts` table (`processing_transcripts`)
2. Knowledge-graph extraction (chunked) → `events`, `entities`, `relationships` tables (`processing_graph`)
3. Mark `completed`

The UI polls `GET /meetings/<id>` to track `graph_processing_status` and display progress.

#### Chunked extraction strategy

The full list of processed transcripts is split into windows of at most `_CHUNK_SIZE = 50` sentences (see [memory_graph/processing.py](src/minute_bot/memory_graph/processing.py)). Each window is sent to the LLM independently so context fits within the model window and extraction quality stays high even for long meetings.

- **Entities** are inserted with `get_or_create`, so the same entity is never duplicated in the DB even if the LLM mentions it across multiple chunks.
- **Entity name→id map** accumulates across all chunks, so relationships extracted in later chunks can still reference entities first introduced in earlier ones.
- **Events** are inserted per chunk as they are encountered.
- **Relationships** are resolved against the cumulative entity map; any relationship whose entities haven't been seen yet is logged and skipped.

## Memory Graph Module

All knowledge-graph operations go through `minute_bot.memory_graph` — never directly to `minute_bot.db` for graph work.

```python
from minute_bot.memory_graph import MemoryGraph, process_meeting_async

# Trigger post-meeting graph processing
process_meeting_async(meeting_id)

# Query graph data
graph = MemoryGraph()
entities      = graph.get_entities(meeting_id)
events        = graph.get_events(meeting_id)
relationships = graph.get_relationships(meeting_id)
action_items  = graph.get_action_items(meeting_id)

# Triplet store
triplet = graph.insert_triplet(record, embedding)
graph.create_triplet_links(triplet)
results = graph.search_triplets(query_embedding, threshold=0.78, k=10)
snapshot = graph.get_snapshot(meeting_id, sequence)
```

Internal modules:
- `memory_graph/extraction.py` — LLM agent that extracts events/entities/relationships from processed transcripts
- `memory_graph/processing.py` — orchestrates the two pipeline steps with status updates

## LLM Agents

Agents live in `src/minute_bot/agents/` (one file per agent). Each module defines:
- `SYSTEM_PROMPT` — full prompt engineering
- `run()` — calls Anthropic API, returns structured output
- Agent-specific model/token constants

| Agent | Location | Input | Output |
|-------|----------|-------|--------|
| `transcript_cleanup` | `agents/transcript_cleanup.py` | Raw Whisper segments + remainder | `{sentences, remainder}` |
| Graph extraction | `memory_graph/extraction.py` | Processed transcripts | `{events, entities, relationships}` |

Both agents use the Anthropic client from `minute_bot.llm.client` and the `llm_model` setting (default: `claude-haiku-4-5-20251001`).

## Triplet Store

The triplet store records `subject → predicate → object` facts extracted from meetings with:
- **Temporal validity** (`valid_from` / `valid_until` sequence numbers)
- **1536-dim vector embeddings** for semantic search (HNSW index, cosine similarity)
- **Auto-links** between related triplets (subject_match, object_match, subject_object edges)

### Tables

| Table | Description |
|-------|-------------|
| `triplets` | Subject-predicate-object facts with embeddings and temporal bounds |
| `triplet_links` | Directed edges between triplets (subject_match / object_match / subject_object) |

### Postgres RPC Functions (via Supabase)

| Function | Description |
|----------|-------------|
| `search_triplets(embedding, threshold, k)` | Cosine similarity search over HNSW index |
| `get_snapshot(meeting_id, sequence)` | All triplets valid at a given sequence point |
| `get_entity_context(entity_id)` | All triplets where entity appears as subject or object |
| `get_open_tasks()` | All open `assigned_to` triplets without `valid_until` |

### Storage Buckets (TripletStorageDB)

| Bucket | Purpose |
|--------|---------|
| `meeting-audio` | Per-speaker audio files |
| `meeting-transcripts` | Transcript JSON and raw text artefacts |

## Speaker Profiling

Speaker profiles are global (not tied to any single meeting). Enroll voices before meetings start:

```bash
python client.py --enroll "Alice"   # records 10 seconds, sends to /profiles/enroll
```

During each meeting's diarization pass, the server:
1. Extracts a 512-dim voice embedding from the speaker's audio segment (Pyannote embedding model)
2. Queries `speaker_profiles` via `match_speaker_profiles()` Postgres function (cosine similarity ≥ 0.7)
3. Names the speaker with their profile name (or "Unidentified Speaker" if no match)
4. Stores both the resolved name and embedding in the per-meeting `speakers` table

Profile matching only runs once per speaker label per session (result cached in memory).

## Redis Pub/Sub Channels

| Channel | Setting key | Publisher | Consumers |
|---------|-------------|-----------|-----------|
| `audio:chunks` | `audio_channel` | `client.py` (HTTP→Redis) | Transcriber, Diarizer |
| `transcription:segments` | `transcript_channel` | `transcriber.py` | SSE `/events/stream` |
| `diarization:segments` | `diarization_channel` | `diarizer.py` | SSE `/events/stream` |
| `graph:events` | `graph_channel` | `pubsub/graph_publisher.py` | SSE `/events/stream` |

The SSE endpoint (`/events/stream`) subscribes to `transcription:segments`, `diarization:segments`, and `graph:events` and forwards events to the client filtered by `session_id`.

## Supabase Database Schema

11 tables across 8 migrations:

| Table | Purpose |
|-------|---------|
| **meetings** | Session/meeting container (includes `speaker_attribution_status`, `graph_processing_status`) |
| **audio_files** | Audio recording metadata + signed URL generation |
| **transcripts** | Raw speech-to-text output (Whisper segments) |
| **processed_transcripts** | LLM-reflowed clean sentences with speaker attribution |
| **speakers** | Per-meeting identified speakers with 512-dim voice embeddings (pgvector) |
| **speaker_profiles** | Global pre-enrolled speaker identities with 512-dim embeddings (pgvector) |
| **events** | Classified semantic meeting events (decision, action_item, etc.) |
| **entities** | Extracted named things (people, tools, documents, etc.) |
| **relationships** | Directed connections between entities |
| **triplets** | Subject-predicate-object facts with 1536-dim embeddings and temporal bounds |
| **triplet_links** | Directed edges between related triplets |

SQL migrations must be applied in order via the Supabase SQL Editor. See `supabase/migrations/`.

## Memory Graph Schema

### Event Types
`action_item`, `decision`, `task_assignment`, `task_reassignment`, `task_cancellation`, `question`, `answer`, `proposal`, `agreement`, `disagreement`, `issue`, `resolution`, `status_update`, `deadline`, `priority_change`, `dependency`, `command`

### Entity Types
- **People**: `person`, `speaker`, `assignee`, `owner`, `reviewer`, `stakeholder`
- **Artifacts**: `document`, `presentation`, `spreadsheet`, `ticket`, `code_repository`, `url`, `dataset`, `tool`, `organization`

### Relationship Types
`said_by`, `assigned_to`, `refers_to`, `depends_on`, `blocks`, `resolves`, `overrides`, `follows_from`, `contradicts`, `supports`, `happens_at`, `part_of`, `discussed_in`

## Configuration

Environment variables loaded from `.env` via pydantic-settings:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Supabase (use service-role key for server-side writes)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Supabase Storage
SAVE_AUDIO_TO_STORAGE=true

# Speech processing
WHISPER_MODEL=base                    # tiny | base | small | medium | large
LANGUAGE=en
TRANSCRIPTION_BUFFER_DURATION=5.0    # seconds per Whisper batch
DIARIZATION_BUFFER_DURATION=30.0     # seconds per Pyannote batch
MIN_SPEAKERS=1
MAX_SPEAKERS=10

# HuggingFace (for Pyannote models)
HF_TOKEN=your-hf-token

# Anthropic LLM (transcript cleanup + graph extraction)
ANTHROPIC_API_KEY=your-anthropic-key
LLM_MODEL=claude-haiku-4-5-20251001
LLM_TRANSCRIPT_FLUSH_SECONDS=30.0    # flush transcript buffer every N seconds

# Server
PORT=5000
DEBUG=false
```
