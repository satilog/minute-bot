"""Shared Anthropic client.

Usage
-----
from minute_bot.llm.client import get_client

client = get_client()
response = client.messages.create(
    model=get_settings().llm_model,
    max_tokens=1024,
    messages=[{"role": "user", "content": "..."}],
)

The client is a module-level singleton so the connection pool is shared across
all LLM callers in the process.  A new client is created lazily on first call
so startup is not blocked if ANTHROPIC_API_KEY is not set.
"""

import logging
from typing import Optional

import anthropic

from minute_bot.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    """Return the shared Anthropic client, creating it on first call."""
    global _client
    if _client is None:
        api_key = get_settings().anthropic_api_key
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file to enable LLM features."
            )
        _client = anthropic.Anthropic(api_key=api_key)
        logger.info("Anthropic client initialised (model=%s)", get_settings().llm_model)
    return _client
