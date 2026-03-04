# Minute Bot

An agentic meeting memory system that transforms unstructured meeting audio into structured, speaker-aware knowledge graphs.

## Features

- Real-time audio capture from microphone
- Speech-to-text transcription (faster-whisper)
- Speaker diarization and profile matching (Pyannote)
- LLM-powered transcript cleanup (Anthropic Claude)
- Knowledge-graph extraction: events, entities, relationships
- Temporal triplet store with semantic vector search (pgvector + HNSW)
- Server-Sent Events for real-time UI updates
- Persistent storage with Supabase
- Redis pub/sub for real-time processing pipeline

## Prerequisites

- Python 3.11+
- Redis server
- Supabase account (database + storage)
- HuggingFace account (for Pyannote models)
- Anthropic API key (for transcript cleanup + graph extraction)
- NVIDIA GPU (optional, for faster ML inference)

## Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd minute-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Install the package
pip install -e .
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Supabase (use service-role key — the server writes to all tables)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-service-role-key

# Anthropic (transcript cleanup + knowledge-graph extraction)
ANTHROPIC_API_KEY=sk-ant-...

# HuggingFace (Pyannote diarization models)
HF_TOKEN=hf_...

# Optional — see all settings below
WHISPER_MODEL=base
SAVE_AUDIO_TO_STORAGE=true
```

See the full [Environment Variables](#environment-variables) table below.

### 3. Set Up Supabase

See the [Supabase Setup](#supabase-setup) section.

### 4. Start Redis

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or install locally
# Ubuntu: sudo apt install redis-server
# Mac: brew install redis
```

### 5. Run the Application

```bash
# Run directly
minute-bot

# Or with Python
python -m minute_bot.api

# Or with gunicorn (production)
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 "minute_bot.api:create_app()"
```

The API will be available at `http://localhost:5000`.
Interactive API docs (Swagger UI): `http://localhost:5000/docs`.

## Running with Docker

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_HOST` | No | `localhost` | Redis server hostname |
| `REDIS_PORT` | No | `6379` | Redis server port |
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Supabase service-role key |
| `SAVE_AUDIO_TO_STORAGE` | No | `true` | Upload recordings to Supabase Storage |
| `HF_TOKEN` | Yes | — | HuggingFace access token (Pyannote) |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key (transcript cleanup + graph extraction) |
| `LLM_MODEL` | No | `claude-haiku-4-5-20251001` | Claude model for LLM agents |
| `LLM_TRANSCRIPT_FLUSH_SECONDS` | No | `30.0` | Transcript buffer flush interval (seconds) |
| `WHISPER_MODEL` | No | `base` | Whisper model size: `tiny` / `base` / `small` / `medium` / `large` |
| `LANGUAGE` | No | `en` | Transcription language code |
| `TRANSCRIPTION_BUFFER_DURATION` | No | `5.0` | Seconds of audio per Whisper batch |
| `DIARIZATION_BUFFER_DURATION` | No | `30.0` | Seconds of audio per Pyannote batch |
| `MIN_SPEAKERS` | No | `1` | Minimum expected speakers (Pyannote hint) |
| `MAX_SPEAKERS` | No | `10` | Maximum expected speakers (Pyannote hint) |
| `PORT` | No | `5000` | Server port |
| `DEBUG` | No | `false` | Enable Flask debug mode |

## Supabase Setup

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Note your **Project URL** and **service-role key** from Settings > API

### 2. Run Database Migrations

Open the **Supabase SQL Editor** and run the following migration files **in order**:

| File | What it creates |
|------|----------------|
| `supabase/migrations/001_initial_schema.sql` | Core tables, pgvector, `match_speakers` RPC |
| `supabase/migrations/002_speaker_profiles.sql` | Global `speaker_profiles` table |
| `supabase/migrations/003_vector_512.sql` | Resize speaker embeddings to 512-dim |
| `supabase/migrations/003_graph_processing_status.sql` | `graph_processing_status` column on meetings |
| `supabase/migrations/004_speaker_attribution_status.sql` | `speaker_attribution_status` column on meetings |
| `supabase/migrations/005_speakers_profile_fk.sql` | FK: `speakers.profile_id → speaker_profiles.id` |
| `supabase/migrations/006_processed_transcripts.sql` | `processed_transcripts` table |
| `supabase/migrations/007_triplet_schema.sql` | `triplets` + `triplet_links` tables, HNSW index, 4 RPCs |

> All migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`). It is safe to re-run them.

### 3. Create Storage Bucket

The server auto-creates `meeting-audio` and `meeting-transcripts` buckets on first use. Create the primary recordings bucket manually:

1. Go to **Storage** in your Supabase dashboard
2. Create a bucket named `recordings`
3. Set it to **Private**

### 4. Add Credentials to `.env`

```bash
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-service-role-key-here
```

## HuggingFace Setup

Pyannote requires accepting licence terms on HuggingFace:

1. Create an account at [huggingface.co](https://huggingface.co)
2. Accept terms for:
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/embedding](https://huggingface.co/pyannote/embedding)
3. Create an access token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Add to `.env`: `HF_TOKEN=hf_your_token_here`

## Using the Client

The client (`client.py`) runs on the host machine and streams audio from your microphone to the server.

```bash
# Install client dependencies (separate venv recommended)
python3 -m venv .venv-client
.venv-client/bin/pip install -r requirements-client.txt

# Start a meeting (auto-detects HyperX mic, falls back to default)
python client.py

# Set a title
python client.py --title "Weekly Standup"

# Choose a specific microphone
python client.py --list-devices      # list available devices
python client.py --device 2          # use device index 2

# Enroll a speaker profile (records 10 seconds)
python client.py --enroll "Alice"
```

## API Reference

### Primary Workflow

```bash
# Start a meeting
curl -X POST http://localhost:5000/meetings/start \
  -H "Content-Type: application/json" \
  -d '{"title": "Team Standup"}'
# → {"status": "started", "session_id": "...", "meeting_id": "..."}

# Stop a meeting
curl -X POST http://localhost:5000/meetings/stop \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "meeting_id": "..."}'

# Trigger graph processing (after speaker attribution completes)
curl -X POST http://localhost:5000/meetings/<id>/process

# Get meeting summary
curl http://localhost:5000/meetings/<id>

# Health check
curl http://localhost:5000/health
```

### Full Endpoint Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/meetings/start` | POST | Create meeting → `{session_id, meeting_id}` |
| `/meetings/stream` | POST | Send audio chunk `{session_id, audio_data, ...}` |
| `/meetings/stop` | POST | End meeting, save audio, trigger speaker attribution |
| `/meetings/status` | GET | List active recording sessions |
| `/meetings` | GET | List recent meetings (`?limit=10`) |
| `/meetings/<id>` | GET | Full summary including all related data |
| `/meetings/<id>/transcripts` | GET | Raw Whisper transcript segments |
| `/meetings/<id>/processed-transcripts` | GET | LLM-cleaned sentence chunks |
| `/meetings/<id>/speakers` | GET | Identified speakers |
| `/meetings/<id>/speakers/<sid>/name` | PUT | Update a speaker's display name |
| `/meetings/<id>/events` | GET | Semantic events (`?type=` filter) |
| `/meetings/<id>/action-items` | GET | Action-item events only |
| `/meetings/<id>/entities` | GET | Extracted entities (`?type=` filter) |
| `/meetings/<id>/relationships` | GET | Entity relationships |
| `/meetings/<id>/audio` | GET | Audio files with signed download URLs |
| `/meetings/<id>/process` | POST | Trigger LLM cleanup + graph extraction |
| `/meetings/<id>/reprocess` | POST | Re-run speaker attribution |
| `/profiles` | GET | List enrolled speaker profiles |
| `/profiles/enroll` | POST | Enroll a voice sample `{name, audio_data}` |
| `/profiles/<id>` | DELETE | Delete a speaker profile |
| `/events/stream` | GET | SSE stream `?session_id=<id>` |
| `/agent/query` | POST | NL Q&A `{query, session_id, meeting_id}` |
| `/health` | GET | Server health + model load status |
| `/streaming/devices` | GET | List server-side audio devices |
| `/transcription/status` | GET | Transcription pipeline state |
| `/diarization/status` | GET | Diarization pipeline state |

## Post-Meeting Processing Pipeline

After recording stops, processing happens in two stages:

### Stage 1 — Speaker Attribution (automatic)

Runs immediately after `/meetings/stop` in a background thread. Track progress via `speaker_attribution_status` in `GET /meetings/<id>`:

```
null/pending → processing → completed | failed
```

1. Match each speaker's 512-dim voice embedding against global `speaker_profiles` (cosine ≥ 0.7)
2. Attribute raw Whisper segments to speakers by time-overlap with diarization windows
3. Run LLM transcript cleanup → write `processed_transcripts`

### Stage 2 — Graph Extraction (manual)

Triggered by `POST /meetings/<id>/process`. Track progress via `graph_processing_status`:

```
null/pending → processing_transcripts → processing_graph → completed | failed
```

1. LLM transcript cleanup → `processed_transcripts` table
2. Knowledge-graph extraction — transcripts are split into **50-sentence chunks**, each chunk processed by the LLM independently for consistent quality on long meetings → `events`, `entities`, `relationships` tables

## Project Structure

```
minute-bot/
├── src/minute_bot/
│   ├── api/            # Flask REST endpoints (one blueprint per domain)
│   │   ├── meetings.py       # Primary workflow + all meeting data endpoints
│   │   ├── events.py         # SSE /events/stream
│   │   ├── agent.py          # /agent/query
│   │   ├── profiles.py       # Speaker profile management
│   │   └── ...
│   ├── core/           # Audio + ML processing
│   │   ├── transcriber.py        # faster-whisper
│   │   ├── diarizer.py           # Pyannote
│   │   └── speaker_attribution.py  # Post-meeting speaker matching
│   ├── memory_graph/   # Knowledge graph — single public interface
│   │   ├── __init__.py       # MemoryGraph class + process_meeting_async()
│   │   ├── extraction.py     # LLM agent: events/entities/relationships
│   │   └── processing.py     # Chunked pipeline orchestration
│   ├── agents/         # LLM agents (transcript_cleanup)
│   ├── db/             # Database layer — one class per table, unified via MinuteBotDB
│   ├── models/         # Pydantic data models
│   ├── pubsub/         # Redis pub/sub (publisher, subscriber, graph_publisher)
│   ├── audio/          # Audio utilities (encoding, processing, analysis)
│   ├── services.py     # ServiceRegistry — eager ML model init
│   └── config.py       # Centralized configuration (pydantic-settings)
├── supabase/
│   └── migrations/     # 8 SQL migration files (apply in order)
├── tests/
├── client.py           # Host-side audio capture script
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Troubleshooting

### Microphone not found

```bash
python client.py --list-devices    # list available devices
arecord -l                         # Linux: check ALSA devices
sudo apt install portaudio19-dev   # Linux: install PortAudio if missing
```

### Pyannote model download fails

1. Verify you accepted the model terms on HuggingFace
2. Check your `HF_TOKEN` is correct
3. Try: `huggingface-cli login`

### Redis connection refused

```bash
redis-cli ping                              # check if Redis is running
docker run -d -p 6379:6379 redis:7-alpine   # start with Docker
```

### Supabase connection / schema errors

1. Verify `SUPABASE_URL` and `SUPABASE_KEY` (must be service-role key)
2. Check your project is active (not paused)
3. Ensure all 8 migrations have been applied in order

### Graph extraction produces no results

1. Ensure speaker attribution completed first (`speaker_attribution_status = "completed"`)
2. Check `processed_transcripts` exist: `GET /meetings/<id>/processed-transcripts`
3. Verify `ANTHROPIC_API_KEY` is set and valid

## License

MIT
