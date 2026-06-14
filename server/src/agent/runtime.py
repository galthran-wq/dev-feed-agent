"""Orchestration entry points: build a profile, chat, and curate a feed.

Chat and the scheduled feed run through the *same* memory-aware agent and share one
persisted message history, so conversation and feed inform each other. The agent must
be configured (OPENROUTER_API_KEY) — otherwise these raise AppError(503).

Output model: agents deliver user-facing text via the ``send_message`` tool (writing to
``deps.channel``), not by returning a string. ``chat``/``curate_feed``/``build_profile``
take a ``channel`` and the agent talks through it; the return values are for the caller's
bookkeeping/logging, not for delivery.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.channels import Channel
from src.agent.deps import AgentDeps
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.exceptions import AppError
from src.models.postgres.users import UserModel
from src.repositories.agent_messages import AgentMessageRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.users import UserRepository

logger = structlog.get_logger()


def _require_agent() -> None:
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")


def _deps(session: AsyncSession, user: UserModel, channel: Channel | None = None) -> AgentDeps:
    return AgentDeps(
        session=session,
        user_id=user.id,
        github_token=user.github_access_token,
        github_username=user.github_username,
        channel=channel,
    )


async def build_profile(session: AsyncSession, user: UserModel, channel: Channel | None = None) -> str:
    """Run the explore-style sub-agent to (re)build the user's interest profile.

    The profile agent fills the sections, then (if a channel is given) tells the user via
    send_message that the profile is ready. Returns the agent's final text for logging.
    """
    _require_agent()
    agent = agents.make_profile_agent()
    prompt = (
        f"Build the interest profile for GitHub user @{user.github_username}. "
        "Investigate their repos and dependencies, then fill in every profile section. "
        "When done, send the user a short message that their profile is ready."
    )
    async with agent:
        result = await agent.run(prompt, deps=_deps(session, user, channel))
    await ProfileRepository(session).mark_built(user.id)
    logger.info("profile_built", user_id=str(user.id))
    return result.output


async def build_profile_safe(user_id: UUID, channel: Channel | None = None) -> None:
    """Fire-and-forget profile build with its own session (first connect, /init, /rebuild)."""
    try:
        async with AsyncSessionLocal() as session:
            user = await UserRepository(session).get_user(user_id)
            if user is not None and user.github_username:
                await build_profile(session, user, channel)
    except Exception as exc:
        logger.warning("profile_build_failed", user_id=str(user_id), error=str(exc))


async def chat(session: AsyncSession, user: UserModel, message: str, channel: Channel | None = None) -> None:
    """Handle one chat turn against the shared, persisted message history.

    The agent replies to the user via the send_message tool (``channel``); this returns
    nothing. A turn that ends without sending anything is logged as suspicious.
    """
    _require_agent()
    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = await agents.make_chat_agent()
    deps = _deps(session, user, channel)
    async with agent:
        result = await agent.run(message, message_history=history, deps=deps)

    await msg_repo.append(user.id, result.new_messages_json())
    if deps.sent_count == 0:
        # Interactive turn produced no message — likely the model forgot send_message.
        logger.warning("agent_turn_no_output", user_id=str(user.id))


async def compact(session: AsyncSession, user: UserModel) -> str:
    """/compact — summarize stored history into a single note, freeing context."""
    _require_agent()
    msg_repo = AgentMessageRepository(session)
    # Pull as much history as we can to summarize it (bounded so compaction itself stays sane).
    history = await msg_repo.load(user.id, max_tokens=100_000, max_runs=1000)
    if not history:
        return "Nothing to compact yet."
    agent = agents.make_summarizer_agent()
    async with agent:
        result = await agent.run("Summarize the conversation so far.", message_history=history)
    await msg_repo.replace_with_summary(user.id, result.output)
    logger.info("history_compacted", user_id=str(user.id))
    return result.output


async def reset(session: AsyncSession, user: UserModel) -> None:
    """/reset — clear conversation history (the interest profile is kept)."""
    await AgentMessageRepository(session).clear(user.id)
    logger.info("history_reset", user_id=str(user.id))


async def curate_feed(session: AsyncSession, user: UserModel, channel: Channel | None = None) -> int:
    """Assemble the feed as a synthetic turn through the shared agent.

    The agent gathers candidates, records them via record_feed_items (the dedup ledger),
    and — if there's anything fresh worth sending — delivers the digest via send_message
    (``channel``). Returns the number of newly-recorded items (0 = nothing fresh).
    """
    _require_agent()
    profile_md = await ProfileRepository(session).get_markdown(user.id)

    explore_n = round(settings.feed_size * settings.explore_ratio)
    exploit_n = max(settings.feed_size - explore_n, 0)
    prompt = (
        "It's time to assemble this user's scheduled feed.\n\n"
        f"Their interest profile:\n{profile_md}\n\n"
        "Gather fresh, relevant items across your sources (GitHub issues/repos, HuggingFace, "
        "Hacker News, arXiv, Reddit). Aim for about "
        f"{exploit_n} 'exploit' items (squarely their interests) and {explore_n} 'explore' items "
        "(adjacent new horizons). First check what was already shown and skip it. Record everything "
        "you decide to surface with record_feed_items, then send the user a concise, friendly "
        "plain-text digest of those items with links via send_message. If nothing new is worth "
        "sending, record nothing and send NOTHING (do not message the user)."
    )

    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = await agents.make_chat_agent()
    deps = _deps(session, user, channel)
    async with agent:
        result = await agent.run(prompt, message_history=history, deps=deps)

    await msg_repo.append(user.id, result.new_messages_json())
    # `recorded` is the authoritative tally of what the agent surfaced this run.
    new_items = len(deps.recorded)
    if new_items > 0 and deps.sent_count == 0:
        # Recorded items but sent nothing — the digest was dropped; surface it.
        logger.warning("feed_recorded_without_send", user_id=str(user.id), new_items=new_items)
    logger.info("feed_curated", user_id=str(user.id), new_items=new_items, sent=deps.sent_count)
    return new_items
