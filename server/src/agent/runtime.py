"""Orchestration entry points: build a profile, chat, and curate a feed.

Chat and the scheduled feed run through the *same* memory-aware agent and share one
persisted message history, so conversation and feed inform each other. The agent must
be configured (OPENROUTER_API_KEY) — otherwise these raise AppError(503).
"""

from uuid import UUID

import structlog
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.deps import AgentDeps
from src.agent.history import sanitize_messages_for_storage
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


def _sanitized_new_messages_json(result: AgentRunResult[str]) -> bytes:
    """Serialize a run's new messages with oversized tool *results* truncated for storage.

    The live run already saw full tool output; only what is PERSISTED for later replay is
    trimmed, isolating raw feed/chat tool payloads from authenticated chat turns (#11).
    """
    sanitized = sanitize_messages_for_storage(result.new_messages(), settings.agent_history_tool_result_max_chars)
    return ModelMessagesTypeAdapter.dump_json(sanitized)


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
    """Handle one chat turn against the shared, persisted message history."""
    _require_agent()
    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = agents.make_chat_agent()
    async with agent:
        result = await agent.run(message, message_history=history, deps=_deps(session, user))

    await msg_repo.append(user.id, _sanitized_new_messages_json(result))
    return result.output


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


async def curate_feed(session: AsyncSession, user: UserModel) -> tuple[str, list[tuple[str, str]]]:
    """Assemble the feed as a synthetic turn through the shared agent.

    Returns ``(digest_text, recorded_keys)`` — the free-form digest to deliver and the
    ``(source, external_id)`` keys the agent newly recorded this run (empty means nothing
    fresh, skip delivery). The agent records what it surfaces via the record_feed_items
    tool as "pending"; the feed pass flips those keys to "delivered" only after a
    successful send, keeping the dedup ledger and delivery reconciled.
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
        "you decide to surface with record_feed_items, then write a concise, friendly plain-text "
        "digest of those items with links. If nothing new is worth sending, record nothing and "
        "reply with a short 'nothing new' note."
    )

    msg_repo = AgentMessageRepository(session)
    history = await msg_repo.load(user.id, max_tokens=settings.agent_history_token_budget)

    agent = agents.make_chat_agent()
    deps = _deps(session, user)
    async with agent:
        result = await agent.run(prompt, message_history=history, deps=deps)

    await msg_repo.append(user.id, _sanitized_new_messages_json(result))
    # `recorded` is the authoritative record of what the agent surfaced this run; the keys
    # let the feed pass mark exactly these items delivered once they actually reach the user.
    recorded_keys = [(r["source"], r["external_id"]) for r in deps.recorded if r.get("source") and r.get("external_id")]
    if not recorded_keys and len(result.output.strip()) > 80:
        # A substantive digest but nothing recorded usually means a skipped record_feed_items
        # call — surface it rather than silently dropping the feed.
        logger.warning("feed_digest_without_record", user_id=str(user.id))
    logger.info("feed_curated", user_id=str(user.id), new_items=len(recorded_keys))
    return result.output, recorded_keys
