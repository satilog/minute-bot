# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Minute Bot is an agentic meeting memory system that transforms unstructured meeting audio into structured, speaker-aware, temporally interpretable knowledge graphs. The system processes meeting audio to identify speakers, transcribe speech, extract events/actions, and build a queryable memory graph.

## Architecture

The system is a consolidated Python application with modular components:

```
┌─────────────────────────────────────────────────────────────┐
│                      Minute Bot API                          │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐     │
│  │ Streaming │  │ Transcription│  │ Speaker Diarization│     │
│  │  /start   │  │   /transcribe│  │    /diarize        │     │
│  │  /stop    │  │   /status    │  │    /speakers       │     │
│  └──────────┘  └──────────────┘  └────────────────────┘     │
│                         │                                    │
│                         ▼                                    │
│                ┌─────────────────┐                          │
│                │  Redis Pub/Sub  │                          │
│                └─────────────────┘                          │
│                         │                                    │
│    ┌───────────────────┬┴──────────────────┐                │
│    ▼                   ▼                   ▼                │
│ ┌──────────┐    ┌──────────────┐    ┌──────────────┐       │
│ │ Supabase │    │   Whisper    │    │   Pyannote   │       │
│ │ Storage  │    │   (STT)      │    │ (Diarization)│       │
│ └──────────┘    └──────────────┘    └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
minute-bot/
├── pyproject.toml          # Python package definition
├── docker-compose.yml      # Container orchestration
├── Dockerfile              # Application container
│
├── src/minute_bot/
│   ├── api/                # Flask REST endpoints
│   │   ├── health.py       # Health check routes
│   │   ├── streaming.py    # Audio capture control
│   │   ├── transcription.py# Transcription endpoints
│   │   ├── diarization.py  # Speaker endpoints
│   │   └── meetings.py     # Meeting CRUD
│   │
│   ├── core/               # Core processing logic
│   │   ├── audio_capture.py    # PyAudio microphone capture
│   │   ├── audio_buffer.py     # Audio chunk accumulation
│   │   ├── transcriber.py      # Whisper transcription
│   │   └── diarizer.py         # Pyannote diarization
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
│   │   ├── speakers.py     # SpeakersDB (pgvector)
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
│   └── config.py           # Centralized configuration
│
├── supabase/
│   └── migrations/         # Database schema
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
```

## Key Technologies

- **Speech-to-Text**: Whisper (OpenAI)
- **Speaker Diarization**: Pyannote
- **Relational Database**: Supabase (PostgreSQL with pgvector)
- **File Storage**: Supabase Storage (audio files)
- **Message Broker**: Redis pub/sub
- **Web Framework**: Flask

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/streaming/start` | POST | Start audio capture |
| `/streaming/stop` | POST | Stop audio capture |
| `/streaming/status` | GET | Capture status |
| `/streaming/devices` | GET | List audio devices |
| `/transcription/start` | POST | Start transcription processing |
| `/transcription/stop` | POST | Stop transcription processing |
| `/transcription/transcribe` | POST | Direct transcription |
| `/diarization/start` | POST | Start diarization processing |
| `/diarization/stop` | POST | Stop diarization processing |
| `/diarization/speakers/{meeting_id}` | GET | Get speakers |
| `/meetings` | GET | List meetings |
| `/meetings/{id}` | GET | Get meeting details |

## Supabase Database Schema

8 core tables for structured data:

| Table | Purpose |
|-------|---------|
| **meetings** | Session/meeting container |
| **audio_files** | Audio recording metadata |
| **transcripts** | Speech-to-text output |
| **speakers** | Identified speakers with voice embeddings (pgvector) |
| **events** | Classified semantic events |
| **entities** | Extracted people, artifacts |
| **relationships** | Connections between entities |
| **entity_mentions** | Where entities are referenced |

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
