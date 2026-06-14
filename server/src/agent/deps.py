from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from src.agent.channels import Channel


@dataclass
class AgentDeps:
    """Per-run context handed to every tool: DB session + the acting user's GitHub identity.

    ``recorded`` accumulates the feed items the agent logged this run (via
    record_feed_items) — the authoritative source for "what was surfaced", decoupled
    from a global row count so concurrent runs can't inflate it.

    ``channel`` is where the agent sends user-facing text (via the send_message tool);
    ``sent_count`` tracks how many messages it sent this run (for observability — an
    interactive turn that sends nothing is suspicious).
    """

    session: AsyncSession
    user_id: UUID
    github_token: str | None = None
    github_username: str | None = None
    recorded: list[dict[str, str]] = field(default_factory=list)
    channel: Channel | None = None
    sent_count: int = 0
