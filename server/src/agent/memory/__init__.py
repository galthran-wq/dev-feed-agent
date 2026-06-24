"""Long-term memory backed by mem0 (OSS, over pgvector in our Postgres)."""

from src.agent.memory.mem0_store import get_mem0

__all__ = ["get_mem0"]
