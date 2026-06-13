from uuid import UUID

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.agent_messages import AgentMessageModel


class AgentMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, user_id: UUID, max_runs: int = 20) -> list[ModelMessage]:
        """Replayable history: the last ``max_runs`` runs' messages, chronological.

        Whole runs are kept (never split) so tool-call/tool-result pairs stay intact.
        """
        result = await self.session.execute(
            select(AgentMessageModel.data)
            .where(AgentMessageModel.user_id == user_id)
            .order_by(AgentMessageModel.created_at.desc())
            .limit(max_runs)
        )
        rows = list(result.scalars().all())
        messages: list[ModelMessage] = []
        for data in reversed(rows):  # back to chronological order
            messages.extend(ModelMessagesTypeAdapter.validate_json(data))
        return messages

    async def append(self, user_id: UUID, data: bytes) -> None:
        """Persist one run's new messages (``result.new_messages_json()``)."""
        self.session.add(AgentMessageModel(user_id=user_id, data=data.decode("utf-8")))
        await self.session.commit()
