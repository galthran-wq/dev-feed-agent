"""Orchestration entry points: chat, curate_feed, compact, reset. Chat and the scheduled
feed share one agent and one persisted history. Agents deliver via the send_message tool
(deps.channel), not via return values; returns are for the caller's bookkeeping.

Profile building is no longer a top-level entry point — it's the ``profile_build`` sub-agent
kind (src/agent/subagents.py) that the chat agent spawns when it sees an empty profile."""

import asyncio
from dataclasses import replace
from uuid import UUID

import structlog
from pydantic_ai.messages import ModelMessage, ModelRequest, SystemPromptPart, UserPromptPart
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.channels import Channel
from src.agent.deps import AgentDeps
from src.agent.memory import get_mem0
from src.core.config import settings
from src.core.exceptions import AppError
from src.models.postgres.users import UserModel
from src.repositories.agent_messages import AgentMessageRepository
from src.repositories.profiles import ProfileRepository

logger = structlog.get_logger()

_FACTS_SENTINEL = "<!--mem0-facts-->"
_bg_tasks: set[asyncio.Task[None]] = set()


def _require_agent() -> None:
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")


def _prime_history(history: list[ModelMessage], system_text: str) -> list[ModelMessage]:
    """Lead the run with the CURRENT system prompt. pydantic-ai bakes the system prompt into the
    first persisted run and won't refresh it when message_history is passed — so without this,
    prompt changes (formatting, date, structure) never reach a user who already has history.
    Strip any stored system parts (and any stale mem0 recall block) and prepend the fresh prompt."""
    cleaned: list[ModelMessage] = []
    for m in history:
        if isinstance(m, ModelRequest):
            kept = [p for p in m.parts if not _is_droppable_part(p)]
            if kept:
                cleaned.append(replace(m, parts=kept))
        else:
            cleaned.append(m)
    return [ModelRequest(parts=[SystemPromptPart(content=system_text)]), *cleaned]


def _is_droppable_part(part: object) -> bool:
    if isinstance(part, SystemPromptPart):
        return True
    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
        return part.content.startswith(_FACTS_SENTINEL)
    return False


async def _recall(user_id: UUID, query: str) -> str | None:
    mem = get_mem0()
    if mem is None or not query.strip():
        return None
    try:
        res = await mem.search(query=query, filters={"user_id": str(user_id)}, top_k=settings.mem0_search_limit)
    except Exception as exc:
        logger.warning("mem0_search_failed", user_id=str(user_id), error=str(exc))
        return None
    results = res.get("results", []) if isinstance(res, dict) else res
    facts = [r.get("memory") for r in results if r.get("memory")]
    if not facts:
        return None
    lines = "\n".join(f"- {f}" for f in facts)
    return f"{_FACTS_SENTINEL}\n## Relevant facts about the user\n{lines}"


def _append_facts(primed: list[ModelMessage], facts: str | None) -> list[ModelMessage]:
    if not facts:
        return primed
    return [*primed, ModelRequest(parts=[UserPromptPart(content=facts)])]


def _remember(user_id: UUID, user_text: str, assistant_text: str) -> None:
    mem = get_mem0()
    if mem is None or not (user_text.strip() and assistant_text.strip()):
        return

    async def _run() -> None:
        try:
            await mem.add(
                messages=[
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ],
                user_id=str(user_id),
            )
        except Exception as exc:
            logger.warning("mem0_add_failed", user_id=str(user_id), error=str(exc))

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


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
    primed = _prime_history(history, agents.build_chat_system_prompt(channel))
    primed = _append_facts(primed, await _recall(user.id, message))
    async with agent:
        result = await agent.run(message, message_history=primed, deps=deps)

    await msg_repo.append(user.id, result.new_messages_json())
    assistant_text = "\n\n".join(deps.sent_texts)
    if deps.sent_count == 0:
        # Interactive turn sent nothing — the model answered in its output instead of calling
        # send_message. Don't leave the user hanging: deliver that output directly.
        fallback = (result.output or "").strip()
        if fallback and channel is not None:
            logger.warning("agent_turn_fallback_send", user_id=str(user.id))
            await channel.send(fallback)
            assistant_text = fallback
        else:
            logger.warning("agent_turn_no_output", user_id=str(user.id))
    _remember(user.id, message, assistant_text)


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
    deps = _deps(session, user, channel)
    primed = _prime_history(history, agents.build_chat_system_prompt(channel))
    primed = _append_facts(primed, await _recall(user.id, profile_md))
    async with agent:
        result = await agent.run(prompt, message_history=primed, deps=deps)

    await msg_repo.append(user.id, result.new_messages_json())
    new_items = len(deps.recorded)
    if new_items > 0 and deps.sent_count == 0:
        # Recorded items but sent nothing — the digest was dropped; surface it.
        logger.warning("feed_recorded_without_send", user_id=str(user.id), new_items=new_items)
    logger.info("feed_curated", user_id=str(user.id), new_items=new_items, sent=deps.sent_count)
    return new_items, deps.sent_count
