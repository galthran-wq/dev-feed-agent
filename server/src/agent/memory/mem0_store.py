"""Shared mem0 client: in-process AsyncMemory over pgvector + OpenRouter. get_mem0() returns
None when the agent is off (no OpenRouter key)."""

from typing import TYPE_CHECKING, Any

import structlog
from src.core.config import settings

if TYPE_CHECKING:
    from mem0 import AsyncMemory

logger = structlog.get_logger()

_mem: "AsyncMemory | None" = None


def _config() -> dict[str, Any]:
    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "user": settings.postgres_user,
                "password": settings.postgres_password,
                "host": settings.postgres_host,
                "port": settings.postgres_port,
                "dbname": settings.postgres_db,
                "collection_name": "mem0_memories",
                "embedding_model_dims": settings.mem0_embed_dims,
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.mem0_chat_model,
                "api_key": settings.openrouter_api_key,
                "openai_base_url": settings.openrouter_base_url,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": settings.mem0_embed_model,
                "api_key": settings.openrouter_api_key,
                "openai_base_url": settings.openrouter_base_url,
                "embedding_dims": settings.mem0_embed_dims,
            },
        },
    }


def get_mem0() -> "AsyncMemory | None":
    global _mem
    if not settings.agent_enabled:
        return None
    if _mem is None:
        from mem0 import AsyncMemory

        _mem = AsyncMemory.from_config(_config())
        logger.info("mem0_initialized")
    return _mem
