"""Agent-facing tools over the user's long-term memory (mem0).

Routine remembering is *passive* — the runtime auto-recalls relevant facts into context and
auto-extracts new ones after each turn (see src/agent/runtime.py), so the agent no longer has
to manage memory by hand. These two tools are the deliberate escape hatches:
- ``add_memory``    — store a fact when the user explicitly asks ("remember this").
- ``search_memory`` — look something up by a CUSTOM query beyond what's already in context.
(Function docstrings below are the tool descriptions the LLM sees — keep them.)"""

import json

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.agent.memory import get_mem0
from src.core.config import settings

logger = structlog.get_logger()


async def add_memory(ctx: RunContext[AgentDeps], text: str) -> str:
    """Explicitly store a durable fact about the user (e.g. they said "remember that ...").

    Routine facts are captured automatically from the conversation — use this only for an
    explicit ask or a fact you don't want to risk losing.
    """
    mem = get_mem0()
    if mem is None:
        return "Memory store is not configured; nothing saved."
    try:
        await mem.add(messages=[{"role": "user", "content": text}], user_id=str(ctx.deps.user_id))
    except Exception as exc:  # best-effort: never surface an internal failure as a tool error
        logger.warning("add_memory_failed", user_id=str(ctx.deps.user_id), error=str(exc))
        return "Could not save that right now."
    return "Saved."


async def search_memory(ctx: RunContext[AgentDeps], query: str) -> str:
    """Semantically search the user's long-term memory for facts matching ``query``.

    Relevant facts for the current message are already injected into your context — reach for
    this when you want a deliberate lookup with a different, custom query (e.g. "have they ever
    mentioned Kafka?"). Returns a JSON array of {id, memory}.
    """
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
