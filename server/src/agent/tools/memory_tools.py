"""Durable-memory tools: the sectioned profile + the feed-item ledger (dedup of what's been shown)."""

import json

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.agent.tools.memory_crud import add_memory, search_memory
from src.models.postgres.profiles import PROFILE_SECTIONS
from src.repositories.feed_items import FeedItemRepository
from src.repositories.profiles import ProfileRepository

logger = structlog.get_logger()


class ShownItem(BaseModel):
    source: str = Field(description="github | hf | hackernews | arxiv | reddit")
    item_type: str = Field(description="repo | issue | help_wanted | paper | model | post | story")
    external_id: str = Field(description="source-scoped stable id (repo full name, arXiv id, HN id, ...)")
    url: str
    title: str
    summary: str | None = None
    reason: str | None = Field(default=None, description="one sentence on why it fits the user")
    bucket: str = Field(default="exploit", description="exploit | explore")


async def read_profile(ctx: RunContext[AgentDeps]) -> str:
    """Read the current interest profile (markdown). Always read before updating."""
    async with ctx.deps.db_lock:
        return await ProfileRepository(ctx.deps.session).get_markdown(ctx.deps.user_id)


async def update_profile_section(ctx: RunContext[AgentDeps], section: str, content: str) -> str:
    """Replace the content of ONE profile section with ``content`` (markdown).

    Valid sections: Summary, Languages & stacks, Domains & topics,
    Notable repos & dependencies, Preferences, Current focus & deep-dives.
    Call this whenever you learn something new or the user states a preference.
    """
    if section not in PROFILE_SECTIONS:
        return f"Unknown section '{section}'. Valid sections: {', '.join(PROFILE_SECTIONS)}"
    async with ctx.deps.db_lock:
        await ProfileRepository(ctx.deps.session).set_section(ctx.deps.user_id, section, content)
    return f"Updated section '{section}'."


async def list_recently_shown(ctx: RunContext[AgentDeps], limit: int = 40) -> str:
    """List items already delivered to the user. Check this before surfacing items so
    you never repeat one."""
    async with ctx.deps.db_lock:
        items = await FeedItemRepository(ctx.deps.session).list_recent(ctx.deps.user_id, limit=limit)
    compact = [
        {"source": i.source, "type": i.item_type, "title": i.title, "url": i.url, "bucket": i.bucket} for i in items
    ]
    return json.dumps(compact, ensure_ascii=False)


async def record_feed_items(ctx: RunContext[AgentDeps], items: list[ShownItem]) -> str:
    """Record the items you've decided to surface, so they're never shown again.

    Call this BEFORE writing the feed digest, with everything you intend to present.
    Already-seen items are skipped automatically; returns the items that were newly
    recorded — write your digest about exactly those.
    """
    recorded: list[dict[str, str]] = []
    async with ctx.deps.db_lock:
        repo = FeedItemRepository(ctx.deps.session)
        keys = [(i.source, i.external_id) for i in items if i.url and i.external_id]
        unseen = await repo.filter_unseen(ctx.deps.user_id, keys)
        for it in items:
            if not (it.url and it.external_id) or (it.source, it.external_id) not in unseen:
                continue
            try:
                await repo.add(
                    ctx.deps.user_id,
                    source=it.source,
                    item_type=it.item_type,
                    external_id=it.external_id,
                    url=it.url,
                    title=it.title,
                    summary=it.summary,
                    reason=it.reason,
                    bucket=it.bucket if it.bucket in ("exploit", "explore") else "exploit",
                )
                recorded.append({"title": it.title, "url": it.url, "bucket": it.bucket})
            except Exception as exc:  # unique race / bad data — skip, keep going
                await ctx.deps.session.rollback()
                logger.warning("record_feed_item_failed", error=str(exc))
    # Authoritative per-run tally the feed pass reads back (see runtime.curate_feed).
    ctx.deps.recorded.extend(recorded)
    return json.dumps({"recorded": recorded, "skipped_already_seen": len(items) - len(recorded)}, ensure_ascii=False)


MEMORY_TOOLS = [read_profile, update_profile_section, list_recently_shown, record_feed_items, search_memory]
MAIN_MEMORY_TOOLS = [add_memory]
