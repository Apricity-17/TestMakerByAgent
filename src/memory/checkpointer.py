"""Checkpointer factory for LangGraph short-term memory."""

from langgraph.checkpoint.memory import MemorySaver


def create_checkpointer() -> MemorySaver:
    """Create an in-memory checkpointer for LangGraph state persistence."""
    return MemorySaver()
