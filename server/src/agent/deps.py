from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Per-run context handed to every tool: DB session + the acting user's GitHub identity."""

    session: AsyncSession
    user_id: UUID
    github_token: str | None = None
    github_username: str | None = None
