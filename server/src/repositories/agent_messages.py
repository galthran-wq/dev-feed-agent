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
        """Recent runs, chronological, token-bounded. Whole runs kept so tool-call/result pairs stay intact;
        the token budget (not run count) is what bounds context since feed runs carry large payloads."""
        result = await self.session.execute(
            select(AgentMessageModel.data)
            .where(AgentMessageModel.user_id == user_id)
            .order_by(AgentMessageModel.created_at.desc())
            .limit(max_runs)
        )
        # Always keep at least one run even if it alone exceeds the budget.
        selected: list[str] = []
        total = 0
        for data in result.scalars().all():
            total += count_tokens(data)
            if selected and total > max_tokens:
                break
            selected.append(data)

        messages: list[ModelMessage] = []
        for data in reversed(selected):
            try:
                messages.extend(ModelMessagesTypeAdapter.validate_json(data))
            except ValueError as exc:
                logger.warning("agent_message_decode_failed", error=str(exc))
        return messages

    async def append(self, user_id: UUID, data: bytes) -> None:
        self.session.add(AgentMessageModel(user_id=user_id, data=data.decode("utf-8")))
        await self.session.commit()

    async def clear(self, user_id: UUID) -> None:
        """Drop all history (/reset)."""
        await self.session.execute(delete(AgentMessageModel).where(AgentMessageModel.user_id == user_id))
        await self.session.commit()

    async def replace_with_summary(self, user_id: UUID, summary: str) -> None:
        """Collapse history to a single system note (/compact)."""
        msg = ModelRequest(parts=[SystemPromptPart(content=f"Summary of earlier conversation:\n{summary}")])
        data = ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")
        await self.session.execute(delete(AgentMessageModel).where(AgentMessageModel.user_id == user_id))
        self.session.add(AgentMessageModel(user_id=user_id, data=data))
        await self.session.commit()
