"""Orchestration entry points: chat, curate_feed, compact, reset. Chat and the scheduled
feed share one agent and one persisted history. Agents deliver via the send_message tool
(deps.channel), not via return values; returns are for the caller's bookkeeping.

Profile building is no longer a top-level entry point — it's the ``profile_build`` sub-agent
kind (src/agent/subagents.py) that the chat agent spawns when it sees an empty profile."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.channels import Channel
from src.agent.deps import AgentDeps
from src.core.config import settings
from src.core.exceptions import AppError
from src.models.postgres.users import UserModel
from src.repositories.agent_messages import AgentMessageRepository
from src.repositories.profiles import ProfileRepository

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


async def chat(session: AsyncSession, user: UserModel, message: str, channel: Channel | None = None) -> None:
    """Handle one chat turn against the shared, persisted message history."""
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


async def curate_feed(session: AsyncSession, user: UserModel, channel: Channel | None = None) -> tuple[int, int]:
    """Assemble the feed as a synthetic agent turn. Returns (new_items recorded, messages sent)."""
    _require_agent()
    profile_md = await ProfileRepository(session).get_markdown(user.id)

    explore_n = round(settings.feed_size * settings.explore_ratio)
    exploit_n = max(settings.feed_size - explore_n, 0)
    prompt = (
        "It's time to assemble this user's scheduled feed. Follow the \"assemble the feed\" turn: "
        "fan out to feed_gather sub-agents, then reduce.\n\n"
        f"Their interest profile:\n{profile_md}\n\n"
        "Spawn several feed_gather sub-agents in parallel (one step), each with a focused task "
        "across your sources (GitHub issues/repos, HuggingFace, Hacker News, arXiv, Reddit) — "
        "split a source into multiple angles when their interests are broad. Consolidate the "
        "candidates they return, drop anything already shown, and pick a balanced set of about "
        f"{exploit_n} 'exploit' items (squarely their interests) and {explore_n} 'explore' items "
        "(adjacent new horizons). Record your final picks with record_feed_items, then send the "
        "user a concise, friendly plain-text digest of those items with links via send_message. "
        "If nothing new is worth sending, record nothing and send NOTHING (do not message the user)."
    )

    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = await agents.make_chat_agent()
    deps = _deps(session, user, channel)
    async with agent:
        result = await agent.run(prompt, message_history=history, deps=deps)

    await msg_repo.append(user.id, result.new_messages_json())
    new_items = len(deps.recorded)
    if new_items > 0 and deps.sent_count == 0:
        # Recorded items but sent nothing — the digest was dropped; surface it.
        logger.warning("feed_recorded_without_send", user_id=str(user.id), new_items=new_items)
    logger.info("feed_curated", user_id=str(user.id), new_items=new_items, sent=deps.sent_count)
    return new_items, deps.sent_count
