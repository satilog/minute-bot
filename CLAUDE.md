# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Minute Bot is an agentic meeting memory system that transforms unstructured meeting audio into structured, speaker-aware, temporally interpretable knowledge graphs. The system processes meeting audio to identify speakers, transcribe speech, extract events/actions, and build a queryable memory graph.

## Architecture

The system has two parts: a server (Docker / Python package) and a thin host-side client script.

```
┌─────────────────────────────────────────────────────────────┐
│  client.py (host)                                           │
│  Captures mic audio → streams chunks to server via HTTP     │
│  --enroll "Name" → enrolls a voice profile                  │
└────────────────────────┬────────────────────────────────────┘
                         │ POST /meetings/stream
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Minute Bot API (server)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Meetings    │  │ Transcription│  │   Diarization    │  │
│  │  /start      │  │  /status     │  │   /status        │  │
│  │  /stream     │  │  /transcribe │  │   /speakers      │  │
│  │  /stop       │  └──────────────┘  └──────────────────┘  │
│  └──────────────┘                                           │
│  ┌──────────────┐                                           │
│  │  Profiles    │  ← global speaker profile enrollment      │
│  │  /enroll     │                                           │
│  │  GET/DELETE  │                                           │
│  └──────────────┘                                           │
│                         │                                   │
│                         ▼                                   │
│                ┌─────────────────┐                         │
│                │  Redis Pub/Sub  │                         │
│                └─────────────────┘                         │
│                         │                                   │
│    ┌───────────────────┬┴──────────────────┐               │
│    ▼                   ▼                   ▼               │
│ ┌──────────┐    ┌──────────────┐    ┌──────────────┐      │
│ │ Supabase │    │   Whisper    │    │   Pyannote   │      │
│ │ Storage  │    │   (STT)      │    │ (Diarization)│      │
│ └──────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

All services (Whisper, Pyannote, Redis pub/sub) are initialized automatically at server startup via `ServiceRegistry` in `services.py`. There are no manual `/start` or `/stop` endpoints for individual services.

## Project Structure

```
minute-bot/
├── pyproject.toml          # Python package definition
├── docker-compose.yml      # Container orchestration
├── Dockerfile              # Application container
├── client.py               # Host-side audio capture script
├── requirements-client.txt # Client dependencies (pyaudio, numpy, requests)
│
├── src/minute_bot/
│   ├── api/                # Flask REST endpoints
│   │   ├── health.py       # Health check + model status
│   │   ├── streaming.py    # Internal audio pipeline helpers
│   │   ├── transcription.py# Transcription status + direct transcribe
│   │   ├── diarization.py  # Speaker diarization status
│   │   ├── profiles.py     # Speaker profile enrollment/management
│   │   └── meetings.py     # Primary workflow: start/stream/stop + data queries
│   │
│   ├── core/               # Core processing logic
│   │   ├── audio_capture.py    # PyAudio microphone capture (server-side, unused in prod)
│   │   ├── audio_buffer.py     # Audio chunk accumulation
│   │   ├── transcriber.py      # Whisper transcription
│   │   └── diarizer.py         # Pyannote diarization + embedding extraction
│   │
│   ├── audio/              # Audio utilities
│   │   ├── encoding.py     # Base64 encode/decode
│   │   ├── processing.py   # Resample, normalize
│   │   └── analysis.py     # Silence detection, RMS
│   │
│   ├── db/                 # Database layer (one file per table)
│   │   ├── client.py       # Supabase client init
│   │   ├── meetings.py     # MeetingsDB
│   │   ├── audio_files.py  # AudioFilesDB + Storage
│   │   ├── transcripts.py  # TranscriptsDB
│   │   ├── speakers.py     # SpeakersDB (per-meeting, pgvector)
│   │   ├── speaker_profiles.py # SpeakerProfilesDB (global, pgvector)
│   │   ├── events.py       # EventsDB
│   │   ├── entities.py     # EntitiesDB
│   │   ├── relationships.py# RelationshipsDB
│   │   └── entity_mentions.py
│   │
│   ├── models/             # Pydantic models (by domain)
│   │   ├── audio.py        # AudioChunk, AudioSegment
│   │   ├── transcription.py# TranscriptionWord, TranscriptionSegment
│   │   ├── speaker.py      # SpeakerSegment, SpeakerProfile
│   │   ├── events.py       # EventType, MeetingEvent
│   │   ├── entities.py     # Entity, Relationship, enums
│   │   ├── session.py      # MeetingSession, ProcessingStatus
│   │   └── records.py      # Database record models
│   │
│   ├── pubsub/             # Redis pub/sub
│   │   ├── client.py       # Redis connection
│   │   ├── publisher.py    # Publish to channels
│   │   └── subscriber.py   # Subscribe and dispatch
│   │
│   ├── services.py         # ServiceRegistry: eager model init at startup
│   └── config.py           # Centralized configuration
│
├── supabase/
│   └── migrations/
│       ├── 001_initial_schema.sql  # Core tables
│       └── 002_speaker_profiles.sql # Global speaker profiles table
│
└── tests/                  # Test suite
```

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
python client.py --device 2            # use a specific device by index
python client.py --title "Standup"     # set meeting title upfront
```

## Key Technologies

- **Speech-to-Text**: Whisper (OpenAI)
- **Speaker Diarization**: Pyannote
- **Relational Database**: Supabase (PostgreSQL with pgvector)
- **File Storage**: Supabase Storage (audio files)
- **Message Broker**: Redis pub/sub
- **Web Framework**: Flask

## API Endpoints

### Primary Workflow

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings/start` | POST | Create meeting, returns `{session_id, meeting_id}` |
| `/meetings/stream` | POST | Receive audio chunk `{session_id, audio_data, ...}` |
| `/meetings/stop` | POST | End meeting, save audio `{session_id, meeting_id}` |
| `/meetings/status` | GET | Active recording sessions |

### Meeting Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings` | GET | List recent meetings |
| `/meetings/<id>` | GET | Full meeting summary |
| `/meetings/<id>/transcripts` | GET | Transcripts for a meeting |
| `/meetings/<id>/speakers` | GET | Speakers for a meeting |
| `/meetings/<id>/events` | GET | Events (optional `?type=` filter) |
| `/meetings/<id>/action-items` | GET | Action items for a meeting |
| `/meetings/<id>/entities` | GET | Entities for a meeting |
| `/meetings/<id>/audio` | GET | Audio files with signed download URLs |
| `/meetings/<id>/speakers/<sid>/name` | PUT | Update speaker display name |

### Speaker Profiles

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/profiles` | GET | List all enrolled speaker profiles |
| `/profiles/enroll` | POST | Enroll voice sample `{name, audio_data}` → 201 |
| `/profiles/<id>` | DELETE | Remove a speaker profile |

### Diagnostics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + model load status |
| `/streaming/devices` | GET | List server-side audio devices |
| `/transcription/status` | GET | Transcription pipeline state |
| `/diarization/status` | GET | Diarization pipeline state |

## Speaker Profiling

Speaker profiles are global (not tied to any single meeting). Enroll voices before meetings start:

```bash
python client.py --enroll "Alice"   # records 10 seconds, sends to /profiles/enroll
```

During each meeting's diarization pass, the server:
1. Extracts a voice embedding from the speaker's audio segment (Pyannote embedding model, 256-dim)
2. Queries `speaker_profiles` via `match_speaker_profiles()` Postgres function (cosine similarity, threshold 0.7)
3. If a match is found, names the speaker with their profile name instead of an anonymous label (SPEAKER_00)
4. Stores both the resolved name and embedding in the per-meeting `speakers` table

Profile matching only runs once per speaker label per session (result cached in memory).

## Supabase Database Schema

9 tables across 2 migrations:

| Table | Purpose |
|-------|---------|
| **meetings** | Session/meeting container |
| **audio_files** | Audio recording metadata |
| **transcripts** | Speech-to-text output |
| **speakers** | Per-meeting identified speakers with voice embeddings (pgvector) |
| **speaker_profiles** | Global pre-enrolled speaker identities (pgvector, meeting-independent) |
| **events** | Classified semantic events |
| **entities** | Extracted people, artifacts |
| **relationships** | Connections between entities |
| **entity_mentions** | Where entities are referenced |

SQL migrations must be applied in order via the Supabase dashboard or `supabase db push`.

## Memory Graph Schema

### Event Types
Action Item, Decision, Task Assignment/Reassignment/Cancellation, Question, Answer, Proposal, Agreement, Disagreement, Issue/Blocker, Resolution, Status Update, Deadline Definition, Priority Change, Dependency, Command/Request

### Entity Types
- **People**: Person, Speaker, Assignee, Owner, Reviewer, Stakeholder
- **Artifacts**: Document, Presentation, Spreadsheet, Ticket, Code Repository, URL, Dataset, Tool

### Relationship Types
said_by, assigned_to, refers_to, depends_on, blocks, resolves, overrides, follows_from, contradicts, supports, happens_at, part_of, discussed_in

## Configuration

Environment variables (can be set via `.env` file):

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Processing
WHISPER_MODEL=base
LANGUAGE=en
TRANSCRIPTION_BUFFER_DURATION=5.0
DIARIZATION_BUFFER_DURATION=30.0

# HuggingFace (for pyannote)
HF_TOKEN=your-hf-token

# Server
PORT=5000
DEBUG=false
```
