"""LLM agents for Minute Bot.

Each module in this package defines one agent:
  - A SYSTEM_PROMPT constant containing the full prompt engineering.
  - A `run()` function that calls the LLM and returns structured output.
  - Agent-specific model / token configuration constants.

Callers import only `run()` and never touch prompt strings directly.

Agents
------
transcript_cleanup   Reflows raw Whisper segments into clean, complete sentences
                     while preserving multi-speaker attribution.

Note: graph extraction logic lives in minute_bot.memory_graph.extraction.
"""
