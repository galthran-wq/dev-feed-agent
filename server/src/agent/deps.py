from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Per-run context handed to every tool: DB session + the acting user's GitHub identity.

    ``recorded`` accumulates the feed items the agent logged this run (via
    record_feed_items) — the authoritative source for "what was surfaced", decoupled
    from a global row count so concurrent runs can't inflate it.
    """

    session: AsyncSession
    user_id: UUID
    github_token: str | None = None
    github_username: str | None = None
    recorded: list[dict[str, str]] = field(default_factory=list)
