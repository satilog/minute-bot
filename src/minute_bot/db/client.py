"""Supabase client initialization."""

from functools import lru_cache

from supabase import Client, create_client

from minute_bot.config import get_settings

STORAGE_BUCKET = "recordings"


@lru_cache
def get_supabase_client() -> Client:
    """Get cached Supabase client instance."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_key)
