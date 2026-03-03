"""Thin wrapper — delegates to the transcript_cleanup agent.

All prompt engineering and LLM call logic lives in:
    minute_bot.agents.transcript_cleanup

This module exists for backward compatibility so existing callers that
import `chunk_segments` do not need to change.
"""

from minute_bot.agents.transcript_cleanup import run as chunk_segments

__all__ = ["chunk_segments"]
