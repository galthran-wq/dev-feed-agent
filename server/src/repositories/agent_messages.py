from uuid import UUID

import structlog
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.agent_messages import AgentMessageModel

logger = structlog.get_logger()


class AgentMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, user_id: UUID, max_runs: int = 20, max_chars: int = 60_000) -> list[ModelMessage]:
        """Replayable history: the most recent runs, chronological, bounded.

        Whole runs are kept (never split) so tool-call/tool-result pairs stay intact.
        Bounded by BOTH a run count and a char budget — feed runs carry large tool
        payloads, so the budget is what actually keeps the context from ballooning.
        A corrupt row is skipped rather than poisoning every future turn.
        """
        result = await self.session.execute(
            select(AgentMessageModel.data)
            .where(AgentMessageModel.user_id == user_id)
            .order_by(AgentMessageModel.created_at.desc())
            .limit(max_runs)
        )
        # Newest-first: keep runs until the char budget is hit (always keep at least one).
        selected: list[str] = []
        total = 0
        for data in result.scalars().all():
            total += len(data)
            if selected and total > max_chars:
                break
            selected.append(data)

        messages: list[ModelMessage] = []
        for data in reversed(selected):  # back to chronological order
            try:
                messages.extend(ModelMessagesTypeAdapter.validate_json(data))
            except ValueError as exc:
                logger.warning("agent_message_decode_failed", error=str(exc))
        return messages

    async def append(self, user_id: UUID, data: bytes) -> None:
        """Persist one run's new messages (``result.new_messages_json()``)."""
        self.session.add(AgentMessageModel(user_id=user_id, data=data.decode("utf-8")))
        await self.session.commit()
