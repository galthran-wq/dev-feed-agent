from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.chat_messages import ChatMessageModel


class ChatMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: UUID, role: str, content: str) -> ChatMessageModel:
        message = ChatMessageModel(user_id=user_id, role=role, content=content)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def list_recent(self, user_id: UUID, limit: int = 20) -> list[ChatMessageModel]:
        """Return the most recent messages in chronological (oldest-first) order."""
        result = await self.session.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.user_id == user_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
