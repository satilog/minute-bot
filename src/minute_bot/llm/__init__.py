"""LLM integration for Minute Bot.

Provides a shared Anthropic client and task-specific processors.
New LLM-powered features should add a module here and use `get_client()`
rather than instantiating Anthropic directly.
"""

from minute_bot.llm.client import get_client

__all__ = ["get_client"]
