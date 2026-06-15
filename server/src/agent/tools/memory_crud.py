"""CRUD tools over the agent's *memories* — specific/local facts, distinct from the
sectioned profile (general/persistent, edited via update_profile_section).
(Function docstrings below are the tool descriptions the LLM sees — keep them.)"""

import json
from uuid import UUID

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.repositories.memories import MemoryRepository

logger = structlog.get_logger()


def _parse_id(memory_id: str) -> UUID | None:
    try:
        return UUID(memory_id)
    except (ValueError, AttributeError):
        return None


async def list_memories(ctx: RunContext[AgentDeps]) -> str:
    """List the user's stored memories (id + title), newest first. Read these alongside
    the profile to ground yourself in specific, local facts."""
    async with ctx.deps.db_lock:
        items = await MemoryRepository(ctx.deps.session).list(ctx.deps.user_id)
    compact = [{"id": str(m.id), "title": m.title} for m in items]
    return json.dumps(compact, ensure_ascii=False)


async def search_memories(ctx: RunContext[AgentDeps], query: str) -> str:
    """Find memories whose title or body contains ``query`` (case-insensitive substring)."""
    async with ctx.deps.db_lock:
        items = await MemoryRepository(ctx.deps.session).search(ctx.deps.user_id, query)
    compact = [{"id": str(m.id), "title": m.title} for m in items]
    return json.dumps(compact, ensure_ascii=False)


async def get_memory(ctx: RunContext[AgentDeps], memory_id: str) -> str:
    """Read one memory's full title and body by id."""
    mid = _parse_id(memory_id)
    if mid is None:
        return f"Invalid memory id '{memory_id}'."
    async with ctx.deps.db_lock:
        memory = await MemoryRepository(ctx.deps.session).get(ctx.deps.user_id, mid)
    if memory is None:
        return f"No memory with id '{memory_id}'."
    return json.dumps({"id": str(memory.id), "title": memory.title, "body": memory.body}, ensure_ascii=False)


async def add_memory(ctx: RunContext[AgentDeps], title: str, body: str) -> str:
    """Store a new specific/local fact about the user. Keep the profile for general,
    high-level facts; route narrow, time-bound notes here."""
    async with ctx.deps.db_lock:
        memory = await MemoryRepository(ctx.deps.session).add(ctx.deps.user_id, title, body)
    return f"Added memory '{memory.title}' (id {memory.id})."


async def edit_memory(ctx: RunContext[AgentDeps], memory_id: str, title: str, body: str) -> str:
    """Replace the title and body of an existing memory."""
    mid = _parse_id(memory_id)
    if mid is None:
        return f"Invalid memory id '{memory_id}'."
    async with ctx.deps.db_lock:
        memory = await MemoryRepository(ctx.deps.session).edit(ctx.deps.user_id, mid, title=title, body=body)
    if memory is None:
        return f"No memory with id '{memory_id}'."
    return f"Updated memory '{memory.title}' (id {memory.id})."


async def delete_memory(ctx: RunContext[AgentDeps], memory_id: str) -> str:
    """Delete a memory by id (e.g. it's stale or wrong)."""
    mid = _parse_id(memory_id)
    if mid is None:
        return f"Invalid memory id '{memory_id}'."
    async with ctx.deps.db_lock:
        deleted = await MemoryRepository(ctx.deps.session).delete(ctx.deps.user_id, mid)
    return f"Deleted memory {memory_id}." if deleted else f"No memory with id '{memory_id}'."


MEMORY_CRUD_TOOLS = [list_memories, search_memories, get_memory, add_memory, edit_memory, delete_memory]
