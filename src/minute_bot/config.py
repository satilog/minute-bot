"""Centralized configuration for Minute Bot."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    save_audio_to_storage: bool = True

    # Processing
    whisper_model: str = "base"
    language: str = "en"
    transcription_buffer_duration: float = 5.0
    diarization_buffer_duration: float = 30.0
    min_speakers: int = 1
    max_speakers: int = 10

    # Channels
    audio_channel: str = "audio:chunks"
    transcript_channel: str = "transcription:segments"
    diarization_channel: str = "diarization:segments"
    graph_channel: str = "graph:events"

    # Server
    port: int = 5000
    debug: bool = False

    # HuggingFace (for pyannote)
    hf_token: str = ""

    # LLM (Anthropic)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_transcript_flush_seconds: float = 30.0  # flush buffer when this much audio is accumulated

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
