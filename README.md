# Minute Bot

An agentic meeting memory system that transforms unstructured meeting audio into structured, speaker-aware knowledge graphs.

## Features

- Real-time audio capture from microphone
- Speech-to-text transcription (Whisper)
- Speaker diarization (Pyannote)
- Persistent storage with Supabase
- Redis pub/sub for real-time processing

## Prerequisites

- Python 3.11+
- Redis server
- Supabase account (for database and storage)
- HuggingFace account (for Pyannote models)
- NVIDIA GPU (optional, for faster ML inference)

## Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd minute-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install the package
pip install -e .
```

### 2. Set Up Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your configuration (see [Environment Variables](#environment-variables) below).

### 3. Set Up Supabase

See [Supabase Setup](#supabase-setup) section below.

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

## Running with Docker

```bash
# Set environment variables
cp .env.example .env
# Edit .env with your values

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
| `SUPABASE_URL` | Yes | - | Your Supabase project URL |
| `SUPABASE_KEY` | Yes | - | Supabase anon/service key |
| `HF_TOKEN` | Yes | - | HuggingFace access token (for Pyannote) |
| `WHISPER_MODEL` | No | `base` | Whisper model size (tiny/base/small/medium/large) |
| `LANGUAGE` | No | `en` | Transcription language code |
| `TRANSCRIPTION_BUFFER_DURATION` | No | `5.0` | Seconds of audio to buffer before transcribing |
| `DIARIZATION_BUFFER_DURATION` | No | `30.0` | Seconds of audio to buffer before diarizing |
| `MIN_SPEAKERS` | No | `1` | Minimum expected speakers |
| `MAX_SPEAKERS` | No | `10` | Maximum expected speakers |
| `PORT` | No | `5000` | Server port |
| `DEBUG` | No | `false` | Enable debug mode |
| `SAVE_AUDIO_TO_STORAGE` | No | `true` | Save recordings to Supabase Storage |

## Supabase Setup

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Note your **Project URL** and **anon/public key** from Settings > API

### 2. Run Database Migrations

In the Supabase SQL Editor, run the migration script:

```bash
# The migration file is at:
supabase/migrations/001_initial_schema.sql
```

Or copy the contents of that file into the Supabase SQL Editor and execute.

This creates:
- 8 tables: `meetings`, `audio_files`, `transcripts`, `speakers`, `events`, `entities`, `relationships`, `entity_mentions`
- pgvector extension for voice embeddings
- `match_speakers` function for similarity search
- Realtime subscriptions

### 3. Create Storage Bucket

1. Go to Storage in your Supabase dashboard
2. Create a new bucket called `recordings`
3. Set the bucket to **private** (signed URLs will be used for access)

### 4. Get Your Credentials

Add these to your `.env` file:

```bash
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-key-here
```

## HuggingFace Setup

Pyannote requires accepting license terms and a HuggingFace token:

1. Create account at [huggingface.co](https://huggingface.co)
2. Accept terms for these models:
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/embedding](https://huggingface.co/pyannote/embedding)
3. Create access token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
4. Add to `.env`:

```bash
HF_TOKEN=hf_your_token_here
```

## API Usage

### Start Recording

```bash
curl -X POST http://localhost:5000/streaming/start \
  -H "Content-Type: application/json" \
  -d '{"title": "Team Standup"}'
```

### Stop Recording

```bash
curl -X POST http://localhost:5000/streaming/stop
```

### Start Transcription Processing

```bash
curl -X POST http://localhost:5000/transcription/start
```

### Start Diarization Processing

```bash
curl -X POST http://localhost:5000/diarization/start
```

### Get Meeting Details

```bash
curl http://localhost:5000/meetings/<meeting_id>
```

### Health Check

```bash
curl http://localhost:5000/health
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/streaming/start` | POST | Start audio capture |
| `/streaming/stop` | POST | Stop audio capture |
| `/streaming/status` | GET | Get capture status |
| `/streaming/devices` | GET | List audio input devices |
| `/transcription/start` | POST | Start transcription processing |
| `/transcription/stop` | POST | Stop transcription processing |
| `/transcription/status` | GET | Get transcription status |
| `/transcription/models` | GET | List available Whisper models |
| `/diarization/start` | POST | Start diarization processing |
| `/diarization/stop` | POST | Stop diarization processing |
| `/diarization/status` | GET | Get diarization status |
| `/meetings` | GET | List recent meetings |
| `/meetings/<id>` | GET | Get meeting with all data |
| `/meetings/<id>/transcripts` | GET | Get meeting transcripts |
| `/meetings/<id>/speakers` | GET | Get meeting speakers |
| `/meetings/<id>/audio` | GET | Get meeting audio files |

## Project Structure

```
minute-bot/
├── src/minute_bot/
│   ├── api/           # Flask REST endpoints
│   ├── core/          # Processing logic (Whisper, Pyannote)
│   ├── audio/         # Audio utilities
│   ├── db/            # Database layer (Supabase)
│   ├── models/        # Pydantic data models
│   ├── pubsub/        # Redis pub/sub
│   └── config.py      # Configuration
├── supabase/
│   └── migrations/    # SQL schema
├── tests/
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Troubleshooting

### No audio devices found

Make sure your microphone is connected and accessible:
```bash
# Linux: Check ALSA devices
arecord -l

# Install PortAudio if needed
sudo apt install portaudio19-dev
```

### Pyannote model download fails

1. Verify you accepted the model terms on HuggingFace
2. Check your `HF_TOKEN` is correct
3. Try logging in: `huggingface-cli login`

### Redis connection refused

```bash
# Check if Redis is running
redis-cli ping

# Start Redis
docker run -d -p 6379:6379 redis:7-alpine
```

### Supabase connection fails

1. Verify `SUPABASE_URL` and `SUPABASE_KEY` are correct
2. Check your project is active (not paused)
3. Ensure migrations have been run

## License

MIT
