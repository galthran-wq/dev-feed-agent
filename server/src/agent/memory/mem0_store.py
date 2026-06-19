"""The shared mem0 client — an in-process ``AsyncMemory`` over pgvector (the existing
Postgres) with LLM + embeddings via OpenRouter. Opt-in: ``get_mem0()`` returns ``None`` when
disabled so callers degrade cleanly (tests on SQLite, deployments without a key).

Backend abstraction / Cloud later: the rest of the app only uses ``.add()`` / ``.search()``,
which ``AsyncMemory`` (OSS) and ``AsyncMemoryClient`` (hosted, per-user ``MEM0_API_KEY``) share.
To support "bring your own mem0 token" portability later, this factory grows a Cloud branch
(keyed by the user's stored key) — no runtime changes needed."""

from typing import TYPE_CHECKING, Any

import structlog
from src.core.config import settings

if TYPE_CHECKING:
    from mem0 import AsyncMemory

logger = structlog.get_logger()

_mem: "AsyncMemory | None" = None


def _config() -> dict[str, Any]:
    """mem0 config: pgvector vector store on our Postgres; LLM + embedder via OpenRouter.
    ``embedding_model_dims`` MUST equal the embed model's real dimension (kept in one setting)."""
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
    """The process-wide ``AsyncMemory``, or ``None`` when mem0 is disabled. Built lazily on
    first use so a disabled deployment never imports mem0 or opens a vector-store connection."""
    global _mem
    if not settings.mem0_active:
        return None
    if _mem is None:
        from mem0 import AsyncMemory  # lazy: keep mem0 out of import time when disabled

        _mem = AsyncMemory.from_config(_config())
        logger.info("mem0_initialized", chat_model=settings.mem0_chat_model, embed_model=settings.mem0_embed_model)
    return _mem
