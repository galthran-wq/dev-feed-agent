import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.agent.channels import Channel


@dataclass
class AgentDeps:
    """Per-run context for every tool. ``recorded``: items surfaced this run — per-run (not a
    global count) so concurrent runs can't inflate it. ``channel``: where send_message
    delivers. ``sent_count``: for observability (an interactive turn sending nothing is suspect)."""

    session: AsyncSession
    user_id: UUID
    github_token: str | None = None
    github_username: str | None = None
    recorded: list[dict[str, str]] = field(default_factory=list)
    channel: Channel | None = None
    sent_count: int = 0
    # One shared AsyncSession across the run, but models (e.g. deepseek) emit parallel tool
    # calls that pydantic-ai runs concurrently — and AsyncSession isn't concurrency-safe.
    # DB-touching tools take this lock so their session access is serialized.
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
