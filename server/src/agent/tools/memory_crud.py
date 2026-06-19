"""Manual memory tools (mem0). Routine remembering is passive (see runtime.py); these are the
deliberate escape hatches. The function docstrings are the tool descriptions the LLM sees."""

import json

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.agent.memory import get_mem0
from src.core.config import settings

logger = structlog.get_logger()


async def add_memory(ctx: RunContext[AgentDeps], text: str) -> str:
    """Store a durable fact about the user when they explicitly ask you to remember something.
    Routine facts are captured automatically — use this only for an explicit ask."""
    mem = get_mem0()
    if mem is None:
        return "Memory store is not configured; nothing saved."
    try:
        await mem.add(messages=[{"role": "user", "content": text}], user_id=str(ctx.deps.user_id))
    except Exception as exc:
        logger.warning("add_memory_failed", user_id=str(ctx.deps.user_id), error=str(exc))
        return "Could not save that right now."
    return "Saved."


async def search_memory(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the user's long-term memory for facts matching ``query`` (a custom lookup beyond
    what's already in your context). Returns a JSON array of {id, memory}."""
    mem = get_mem0()
    if mem is None:
        return "[]"
    uid = str(ctx.deps.user_id)
    try:
        res = await mem.search(query=query, filters={"user_id": uid}, top_k=settings.mem0_search_limit)
    except Exception as exc:
        logger.warning("search_memory_failed", user_id=str(ctx.deps.user_id), error=str(exc))
        return "[]"
    results = res.get("results", []) if isinstance(res, dict) else res
    facts = [{"id": r.get("id"), "memory": r.get("memory")} for r in results if r.get("memory")]
    return json.dumps(facts, ensure_ascii=False)
