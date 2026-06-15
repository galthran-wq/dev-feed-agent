"""Sub-agent spawn primitive: the fan-in/fan-out framework's core.

The main agent delegates heavy/multi-step work via the single ``spawn_subagent`` tool, which
calls ``run_subagent`` here. A sub-agent runs its own (resumable) conversation in its own
``subagent_sessions`` row; only a short result string returns to the main agent — its full
trace never enters the main agent's history (context economy). Each ``kind`` differs only by a
system prompt + small post-step; the toolset is shared (BASE_TOOLS, minus spawn_subagent)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from pydantic_ai import AgentRunResult
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents
from src.agent.channels import Channel
from src.agent.deps import AgentDeps
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.profiles import ProfileRepository
from src.repositories.subagent_sessions import SubagentSessionRepository

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage

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


_REGISTRY: dict[str, SubagentSpec] = {
    "profile_build": SubagentSpec(
        prompt_file="profile_builder.md",
        model_name=settings.profile_model,
        default_task=_profile_task,
        # Fall back if the run ended on a tool call with no trailing text part.
        summarize=lambda result: result.output or "Profile built.",
    ),
}


async def _post_step(kind: str, session: AsyncSession, user_id: UUID) -> None:
    if kind == "profile_build":
        await ProfileRepository(session).mark_built(user_id)


@asynccontextmanager
async def _run_session(
    own_session: bool, session: AsyncSession, parent_db_lock: asyncio.Lock | None
) -> AsyncIterator[tuple[AsyncSession, asyncio.Lock]]:
    """Yield the (session, lock) the sub-agent runs on. Nested (default): the caller's session
    + its lock (asyncio.Lock isn't reentrant, so the spawning tool must not hold it). With
    ``own_session`` (reserved for the later feed fan-out): a fresh session + fresh lock so
    parallel siblings don't share one non-concurrency-safe session."""
    if own_session:
        async with AsyncSessionLocal() as sub_session:
            yield sub_session, asyncio.Lock()
    else:
        yield session, parent_db_lock if parent_db_lock is not None else asyncio.Lock()


async def run_subagent(
    kind: str,
    *,
    session: AsyncSession,
    user_id: UUID,
    github_token: str | None,
    github_username: str | None,
    channel: Channel | None,
    task: str | None = None,
    session_id: str | None = None,
    parent_db_lock: asyncio.Lock | None = None,
    own_session: bool = False,
) -> tuple[str, str]:
    """Run (or resume) a ``kind`` sub-agent; return ``(concise_result, session_id)``.

    Resume when ``session_id`` names an existing row, else mint a new session. Persists the
    full trace and never raises — failures come back as a string so the main agent can still
    reply."""
    spec = _REGISTRY.get(kind)
    if spec is None:
        return f"[no such sub-agent kind '{kind}']", session_id or ""

    async with _run_session(own_session, session, parent_db_lock) as (sess, lock):
        repo = SubagentSessionRepository(sess)

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
            session=sess,
            user_id=user_id,
            github_token=github_token,
            github_username=github_username,
            channel=channel,
            db_lock=lock,
        )

        try:
            agent = await agents.make_subagent(spec.prompt_file, spec.model_name)
            async with agent:
                result = await agent.run(task or spec.default_task(github_username), message_history=history, deps=deps)
            await repo.save(sid, result.all_messages_json())
            await _post_step(kind, sess, user_id)
            logger.info("subagent_done", kind=kind, session_id=str(sid), user_id=str(user_id))
            return spec.summarize(result), str(sid)
        except Exception as exc:
            logger.warning("subagent_failed", kind=kind, session_id=str(sid), error=str(exc))
            return f"[sub-agent '{kind}' failed: {exc}]", str(sid)
