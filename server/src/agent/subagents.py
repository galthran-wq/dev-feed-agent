"""Sub-agent spawn primitive: the fan-in/fan-out framework's core.

The main agent delegates heavy/multi-step work via the single ``spawn_subagent`` tool, which
calls ``run_subagent`` here. Each sub-agent runs its own (resumable) conversation in its own
``subagent_sessions`` row and **its own DB session** — so parallel sub-agents are safe by
construction and never share the caller's session. Only a short result string returns to the
main agent; the full trace never enters the main agent's history (context economy). Sub-agents
have no ``send_message`` tool — they report back and the main agent decides what to tell the
user. Each ``kind`` differs only by a system prompt + small post-step."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from pydantic_ai import AgentRunResult
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.deps import AgentDeps
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.profiles import ProfileRepository
from src.repositories.subagent_sessions import SubagentSessionRepository

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from src.agent.trace import LiveTrace

logger = structlog.get_logger()


@dataclass(frozen=True)
class SubagentSpec:
    prompt_file: str
    model_name: str
    default_task: Callable[[str | None], str]  # (github_username) -> task
    summarize: Callable[[AgentRunResult[str]], str]


def _profile_task(github_username: str | None) -> str:
    who = f"@{github_username}" if github_username else "this user"
    return (
        f"Build the interest profile for GitHub user {who}. Investigate their repos and "
        "dependencies, then fill in every profile section. End with one short sentence "
        "summarizing what you learned about their interests."
    )


def _gather_task(github_username: str | None) -> str:
    # Used only if the main agent spawns feed_gather with no task; it normally passes a focused one.
    return (
        "Gather a handful of fresh, relevant feed candidates for this user across the sources "
        "available to you. Read their profile and recently-shown list first, then report the "
        "candidates as a compact list."
    )


_REGISTRY: dict[str, SubagentSpec] = {
    "profile_build": SubagentSpec(
        prompt_file="profile_builder.md",
        model_name=settings.profile_model,
        default_task=_profile_task,
        # Fall back if the run ended on a tool call with no trailing text part.
        summarize=lambda result: result.output or "Profile built.",
    ),
    "feed_gather": SubagentSpec(
        prompt_file="feed_gather.md",
        model_name=settings.agent_model,
        default_task=_gather_task,
        summarize=lambda result: result.output or "(no candidates found)",
    ),
}


async def _post_step(kind: str, session: AsyncSession, user_id: UUID) -> None:
    if kind == "profile_build":
        await ProfileRepository(session).mark_built(user_id)


async def run_subagent(
    kind: str,
    *,
    user_id: UUID,
    github_token: str | None,
    github_username: str | None,
    task: str | None = None,
    session_id: str | None = None,
    tracer: "LiveTrace | None" = None,
) -> tuple[str, str]:
    """Run (or resume) a ``kind`` sub-agent; return ``(concise_result, session_id)``.

    Always runs on its **own** ``AsyncSessionLocal`` + lock, so callers (including N parallel
    spawns) never share a session. Resume when ``session_id`` names an existing row, else mint a
    new session. Persists the full trace and never raises — failures come back as a string so the
    main agent can still reply."""
    spec = _REGISTRY.get(kind)
    if spec is None:
        return f"[no such sub-agent kind '{kind}']", session_id or ""

    async with AsyncSessionLocal() as session:
        repo = SubagentSessionRepository(session)

        sid: UUID | None = None
        if session_id:
            try:
                sid = UUID(session_id)
            except ValueError:
                sid = None
        history: list[ModelMessage] = []
        if sid is not None and await repo.get(sid) is not None:
            history = await repo.load(sid)
        else:
            if session_id:  # asked to resume but the id was invalid/gone — start fresh, note it
                logger.info("subagent_resume_miss", kind=kind, session_id=session_id)
            sid = await repo.create(user_id, kind)

        deps = AgentDeps(
            session=session,
            user_id=user_id,
            github_token=github_token,
            github_username=github_username,
            channel=None,  # sub-agents don't talk to the user; the main agent relays their result
            tracer=tracer,  # but their steps DO surface in the shared live trace
            db_lock=asyncio.Lock(),
        )

        try:
            agent = await agents.make_subagent(spec.prompt_file, spec.model_name)
            # Attribute this sub-agent's tool steps to its kind in the shared trace.
            handler = tracer.make_handler(prefix=f"{kind} ▸ ") if tracer is not None else None
            async with agent:
                result = await agent.run(
                    task or spec.default_task(github_username),
                    message_history=history,
                    deps=deps,
                    event_stream_handler=handler,
                )
            await repo.save(sid, result.all_messages_json())
            await _post_step(kind, session, user_id)
            logger.info("subagent_done", kind=kind, session_id=str(sid), user_id=str(user_id))
            return spec.summarize(result), str(sid)
        except Exception as exc:
            logger.warning("subagent_failed", kind=kind, session_id=str(sid), error=str(exc))
            return f"[sub-agent '{kind}' failed: {exc}]", str(sid)
