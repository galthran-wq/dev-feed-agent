from uuid import UUID

import structlog
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.subagent_sessions import SubagentSessionModel

logger = structlog.get_logger()


class SubagentSessionRepository:
    """Session-keyed store for sub-agent traces. Unlike AgentMessageRepository (append one row
    per run), a session is a single row **overwritten** with its full trace so it can be resumed."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: UUID, kind: str) -> UUID:
        row = SubagentSessionModel(user_id=user_id, kind=kind, data="[]")
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row.id

    async def get(self, session_id: UUID) -> SubagentSessionModel | None:
        result = await self.session.execute(select(SubagentSessionModel).where(SubagentSessionModel.id == session_id))
        return result.scalar_one_or_none()

    async def load(self, session_id: UUID) -> list[ModelMessage]:
        """Full trace of the session, decoded; ``[]`` if missing or unparsable."""
        row = await self.get(session_id)
        if row is None:
            return []
        try:
            return list(ModelMessagesTypeAdapter.validate_json(row.data))
        except ValueError as exc:
            logger.warning("subagent_session_decode_failed", session_id=str(session_id), error=str(exc))
            return []

    async def save(self, session_id: UUID, data: bytes) -> None:
        """Overwrite the session's trace with ``result.all_messages_json()``."""
        row = await self.get(session_id)
        if row is None:
            logger.warning("subagent_session_save_missing", session_id=str(session_id))
            return
        row.data = data.decode("utf-8")
        await self.session.commit()
