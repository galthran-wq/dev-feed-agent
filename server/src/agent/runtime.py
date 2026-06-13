"""Orchestration entry points: build a profile, chat, and curate a feed.

Each opens the right agent, supplies per-user deps, and persists results. The agent
must be configured (OPENROUTER_API_KEY) — otherwise these raise AppError(503).
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.agents import CuratedItem
from src.agent.deps import AgentDeps
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.exceptions import AppError
from src.models.postgres.feed_items import FeedItemModel
from src.models.postgres.users import UserModel
from src.repositories.chat_messages import ChatMessageRepository
from src.repositories.feed_items import FeedItemRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.users import UserRepository

logger = structlog.get_logger()


def _require_agent() -> None:
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")


def _deps(session: AsyncSession, user: UserModel) -> AgentDeps:
    return AgentDeps(
        session=session,
        user_id=user.id,
        github_token=user.github_access_token,
        github_username=user.github_username,
    )


async def build_profile(session: AsyncSession, user: UserModel) -> str:
    """Run the explore-style sub-agent to (re)build the user's interest profile."""
    _require_agent()
    agent = agents.make_profile_agent()
    prompt = (
        f"Build the interest profile for GitHub user @{user.github_username}. "
        "Investigate their repos and dependencies, then fill in every profile section."
    )
    async with agent:
        result = await agent.run(prompt, deps=_deps(session, user))
    await ProfileRepository(session).mark_built(user.id)
    logger.info("profile_built", user_id=str(user.id))
    return result.output


async def build_profile_safe(user_id: UUID) -> None:
    """Fire-and-forget profile build with its own session (used on first connect)."""
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository(session).get_user(user_id)
            if user is not None and user.github_username:
                await build_profile(session, user)
    except Exception as exc:
        logger.warning("profile_build_failed", user_id=str(user_id), error=str(exc))


async def chat(session: AsyncSession, user: UserModel, message: str) -> str:
    """Handle one chat turn: persist it, run the memory-aware agent, persist the reply."""
    _require_agent()
    chat_repo = ChatMessageRepository(session)
    history = await chat_repo.list_recent(user.id, limit=10)
    convo = "\n".join(f"{m.role}: {m.content}" for m in history)
    prompt = (f"Recent conversation:\n{convo}\n\n" if convo else "") + f"User: {message}"

    agent = agents.make_chat_agent()
    async with agent:
        result = await agent.run(prompt, deps=_deps(session, user))

    reply = result.output
    await chat_repo.add(user.id, "user", message)
    await chat_repo.add(user.id, "assistant", reply)
    return reply


async def curate_feed(session: AsyncSession, user: UserModel) -> list[FeedItemModel]:
    """Build today's feed: gather candidates, score/bucket them, dedup, record. No delivery."""
    _require_agent()
    explore_n = round(settings.feed_size * settings.explore_ratio)
    exploit_n = max(settings.feed_size - explore_n, 0)

    profile_md = await ProfileRepository(session).get_markdown(user.id)
    prompt = (
        f"Curate a feed for this developer.\n\nProfile:\n{profile_md}\n\n"
        f"Return up to {exploit_n} 'exploit' items and up to {explore_n} 'explore' items. "
        "Check what was recently shown and do not repeat it. Diversify across sources."
    )

    agent = agents.make_curator_agent()
    async with agent:
        result = await agent.run(prompt, deps=_deps(session, user))

    return await _record_feed(session, user.id, result.output.items)


async def _record_feed(session: AsyncSession, user_id: UUID, items: list[CuratedItem]) -> list[FeedItemModel]:
    """Filter by relevance, drop already-seen items, persist the rest as delivered."""
    feed_repo = FeedItemRepository(session)
    relevant = [i for i in items if i.score >= settings.relevance_threshold and i.url and i.external_id]
    keys = [(i.source, i.external_id) for i in relevant]
    unseen = await feed_repo.filter_unseen(user_id, keys)

    recorded: list[FeedItemModel] = []
    for item in sorted(relevant, key=lambda i: i.score, reverse=True):
        if (item.source, item.external_id) not in unseen:
            continue
        try:
            stored = await feed_repo.add(
                user_id,
                source=item.source,
                item_type=item.item_type,
                external_id=item.external_id,
                url=item.url,
                title=item.title,
                summary=item.summary or None,
                score=item.score,
                reason=item.reason,
                bucket=item.bucket if item.bucket in ("exploit", "explore") else "exploit",
            )
            recorded.append(stored)
        except Exception as exc:  # unique-race or bad data — skip, don't abort the batch
            await session.rollback()
            logger.warning("feed_item_record_failed", error=str(exc))
    return recorded
