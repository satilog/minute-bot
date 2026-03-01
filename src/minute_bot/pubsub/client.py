"""Redis client for pub/sub messaging."""

from functools import lru_cache

import redis

from minute_bot.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """Get cached Redis client instance."""
    settings = get_settings()
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )


def get_redis_client_binary() -> redis.Redis:
    """Get Redis client without decode_responses for binary data."""
    settings = get_settings()
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=False,
    )
