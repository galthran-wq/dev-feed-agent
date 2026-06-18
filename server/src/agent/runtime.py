"""Orchestration entry points: chat, curate_feed, compact, reset. Chat and the scheduled
feed share one agent and one persisted history. Agents deliver via the send_message tool
(deps.channel), not via return values; returns are for the caller's bookkeeping.

Profile building is no longer a top-level entry point — it's the ``profile_build`` sub-agent
kind (src/agent/subagents.py) that the chat agent spawns when it sees an empty profile."""

from dataclasses import replace
from typing import TYPE_CHECKING

import structlog
from pydantic_ai.messages import ModelMessage, ModelRequest, SystemPromptPart
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.channels import Channel
from src.agent.deps import AgentDeps

if TYPE_CHECKING:
    from src.agent.trace import LiveTrace
from src.core.config import settings
from src.core.exceptions import AppError
from src.models.postgres.users import UserModel
from src.repositories.agent_messages import AgentMessageRepository
from src.repositories.profiles import ProfileRepository

logger = structlog.get_logger()


def _require_agent() -> None:
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")


def _prime_history(history: list[ModelMessage], system_text: str) -> list[ModelMessage]:
    """Lead the run with the CURRENT system prompt. pydantic-ai bakes the system prompt into the
    first persisted run and won't refresh it when message_history is passed — so without this,
    prompt changes (formatting, date, structure) never reach a user who already has history.
    Strip any stored system parts and prepend the fresh prompt."""
    cleaned: list[ModelMessage] = []
    for m in history:
        if isinstance(m, ModelRequest):
            kept = [p for p in m.parts if not isinstance(p, SystemPromptPart)]
            if kept:
                cleaned.append(replace(m, parts=kept))
        else:
            cleaned.append(m)
    return [ModelRequest(parts=[SystemPromptPart(content=system_text)]), *cleaned]


def _deps(session: AsyncSession, user: UserModel, channel: Channel | None, tracer: "LiveTrace | None") -> AgentDeps:
    return AgentDeps(
        session=session,
        user_id=user.id,
        github_token=user.github_access_token,
        github_username=user.github_username,
        channel=channel,
        tracer=tracer,
    )


async def chat(session: AsyncSession, user: UserModel, message: str, channel: Channel | None = None) -> None:
    """Handle one chat turn against the shared, persisted message history."""
    _require_agent()
    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = await agents.make_chat_agent()
    tracer = channel.begin_trace() if channel is not None else None
    deps = _deps(session, user, channel, tracer)
    primed = _prime_history(history, agents.build_chat_system_prompt(channel))
    handler = tracer.make_handler() if tracer is not None else None
    try:
        async with agent:
            result = await agent.run(message, message_history=primed, deps=deps, event_stream_handler=handler)
    except Exception:
        if tracer is not None:  # leave the trace showing how far it got, marked failed
            await tracer.finish(ok=False)
        raise
    if tracer is not None:
        await tracer.finish(ok=True)

    await msg_repo.append(user.id, result.new_messages_json())
    if deps.sent_count == 0:
        # Interactive turn sent nothing — the model answered in its output instead of calling
        # send_message. Don't leave the user hanging: deliver that output directly.
        fallback = (result.output or "").strip()
        if fallback and channel is not None:
            logger.warning("agent_turn_fallback_send", user_id=str(user.id))
            await channel.send(fallback)
        else:
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
    # Same freeze applies: with history, the agent's system_prompt is ignored — inject the
    # summarizer prompt so it isn't replaced by a stale chat/summary prompt from history.
    primed = _prime_history(history, agents.SUMMARIZER_PROMPT)
    async with agent:
        result = await agent.run("Summarize the conversation so far.", message_history=primed)
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

    prompt = (
        "It's time to assemble this user's scheduled feed. Follow the \"assemble the feed\" turn: "
        "fan out to feed_gather sub-agents, then reduce.\n\n"
        f"Their interest profile:\n{profile_md}\n\n"
        "Spawn several feed_gather sub-agents in parallel (one step), each with a focused task "
        "across your sources (GitHub issues/repos, HuggingFace, Hacker News, arXiv, Reddit) — "
        "split a source into multiple angles when their interests are broad, and ALWAYS include a "
        "task for GitHub good-first-issues / help-wanted matching their stack. Consolidate the "
        "candidates they return, drop anything already shown, and lean recent (prefer the last "
        "week, keep older gems). There is no fixed item count — surface EVERY fresh, relevant item "
        "that clears the bar (one compact line each keeps it scannable), with a healthy mix of "
        "'exploit' (squarely their interests) and 'explore' (adjacent horizons). Record your final "
        "picks with record_feed_items, then send the compact, theme-grouped digest (one line per "
        "item, per the digest structure) via send_message. If nothing new is worth sending, record "
        "nothing and send NOTHING (do not message the user)."
    )

    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = await agents.make_chat_agent()
    tracer = channel.begin_trace() if channel is not None else None
    deps = _deps(session, user, channel, tracer)
    primed = _prime_history(history, agents.build_chat_system_prompt(channel))
    handler = tracer.make_handler() if tracer is not None else None
    try:
        async with agent:
            result = await agent.run(prompt, message_history=primed, deps=deps, event_stream_handler=handler)
    except Exception:
        if tracer is not None:
            await tracer.finish(ok=False)
        raise
    if tracer is not None:
        await tracer.finish(ok=True)

    await msg_repo.append(user.id, result.new_messages_json())
    new_items = len(deps.recorded)
    if new_items > 0 and deps.sent_count == 0:
        # Recorded items but sent nothing — the digest was dropped; surface it.
        logger.warning("feed_recorded_without_send", user_id=str(user.id), new_items=new_items)
    logger.info("feed_curated", user_id=str(user.id), new_items=new_items, sent=deps.sent_count)
    return new_items, deps.sent_count
