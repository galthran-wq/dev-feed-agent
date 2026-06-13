"""Tools for the agent's durable memory: the sectioned profile + already-shown items.

The profile is the agent's own notebook about the user — it is expected to patch a
section the moment it learns something new or changed, not only during /init.
"""

import json

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.models.postgres.profiles import PROFILE_SECTIONS
from src.repositories.feed_items import FeedItemRepository
from src.repositories.profiles import ProfileRepository

logger = structlog.get_logger()


async def read_profile(ctx: RunContext[AgentDeps]) -> str:
    """Read the current interest profile (markdown). Always read before updating."""
    return await ProfileRepository(ctx.deps.session).get_markdown(ctx.deps.user_id)


async def update_profile_section(ctx: RunContext[AgentDeps], section: str, content: str) -> str:
    """Replace the content of ONE profile section with ``content`` (markdown).

    Valid sections: Summary, Languages & stacks, Domains & topics,
    Notable repos & dependencies, Preferences, Current focus & deep-dives.
    Call this whenever you learn something new or the user states a preference.
    """
    if section not in PROFILE_SECTIONS:
        return f"Unknown section '{section}'. Valid sections: {', '.join(PROFILE_SECTIONS)}"
    await ProfileRepository(ctx.deps.session).set_section(ctx.deps.user_id, section, content)
    return f"Updated section '{section}'."


async def list_recently_shown(ctx: RunContext[AgentDeps], limit: int = 30) -> str:
    """List items already delivered to the user (so you don't repeat them)."""
    items = await FeedItemRepository(ctx.deps.session).list_recent(ctx.deps.user_id, limit=limit)
    compact = [
        {"source": i.source, "type": i.item_type, "title": i.title, "url": i.url, "bucket": i.bucket} for i in items
    ]
    return json.dumps(compact, ensure_ascii=False)


MEMORY_TOOLS = [read_profile, update_profile_section, list_recently_shown]
