from uuid import UUID

import structlog
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest, SystemPromptPart
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent.tokens import count_tokens
from src.models.postgres.agent_messages import AgentMessageModel

logger = structlog.get_logger()


class AgentMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def load(self, user_id: UUID, max_tokens: int = 12000, max_runs: int = 100) -> list[ModelMessage]:
        """Replayable history: the most recent runs, chronological, bounded by a TOKEN budget.

        Whole runs are kept (never split) so tool-call/tool-result pairs stay intact.
        Feed runs carry large tool payloads, so the token budget is what actually keeps
        the replayed context bounded. A corrupt row is skipped, not fatal.
        """
        result = await self.session.execute(
            select(AgentMessageModel.data)
            .where(AgentMessageModel.user_id == user_id)
            .order_by(AgentMessageModel.created_at.desc())
            .limit(max_runs)
        )
        # Newest-first: keep runs until the token budget is hit (always keep at least one).
        selected: list[str] = []
        total = 0
        for data in result.scalars().all():
            total += count_tokens(data)
            if selected and total > max_tokens:
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

    async def clear(self, user_id: UUID) -> None:
        """Drop all stored conversation history for the user (/reset)."""
        await self.session.execute(delete(AgentMessageModel).where(AgentMessageModel.user_id == user_id))
        await self.session.commit()

    async def replace_with_summary(self, user_id: UUID, summary: str) -> None:
        """Collapse history to a single system note carrying ``summary`` (/compact)."""
        msg = ModelRequest(parts=[SystemPromptPart(content=f"Summary of earlier conversation:\n{summary}")])
        data = ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")
        await self.session.execute(delete(AgentMessageModel).where(AgentMessageModel.user_id == user_id))
        self.session.add(AgentMessageModel(user_id=user_id, data=data))
        await self.session.commit()
