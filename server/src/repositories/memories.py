import builtins
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.memories import MemoryModel


class MemoryRepository:
    """CRUD over a user's specific/local memories. Every query is scoped by user_id.

    ``builtins.list`` is used in annotations/bodies because the ``list`` method
    shadows the builtin inside the class scope.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, user_id: UUID) -> builtins.list[MemoryModel]:
        result = await self.session.execute(
            select(MemoryModel).where(MemoryModel.user_id == user_id).order_by(MemoryModel.created_at.desc())
        )
        return builtins.list(result.scalars().all())

    async def search(self, user_id: UUID, query: str) -> builtins.list[MemoryModel]:
        """Naive case-insensitive substring match over title + body. LIKE metacharacters
        in ``query`` (``%`` ``_`` ``\\``) are escaped so a query like ``100%`` matches the
        literal text rather than acting as a wildcard."""
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        result = await self.session.execute(
            select(MemoryModel)
            .where(
                MemoryModel.user_id == user_id,
                or_(
                    MemoryModel.title.ilike(pattern, escape="\\"),
                    MemoryModel.body.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(MemoryModel.created_at.desc())
        )
        return builtins.list(result.scalars().all())

    async def get(self, user_id: UUID, memory_id: UUID) -> MemoryModel | None:
        result = await self.session.execute(
            select(MemoryModel).where(MemoryModel.user_id == user_id, MemoryModel.id == memory_id)
        )
        return result.scalar_one_or_none()

    async def add(self, user_id: UUID, title: str, body: str) -> MemoryModel:
        memory = MemoryModel(user_id=user_id, title=title, body=body)
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def edit(
        self,
        user_id: UUID,
        memory_id: UUID,
        title: str | None = None,
        body: str | None = None,
    ) -> MemoryModel | None:
        memory = await self.get(user_id, memory_id)
        if memory is None:
            return None
        if title is not None:
            memory.title = title
        if body is not None:
            memory.body = body
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def delete(self, user_id: UUID, memory_id: UUID) -> bool:
        memory = await self.get(user_id, memory_id)
        if memory is None:
            return False
        await self.session.delete(memory)
        await self.session.commit()
        return True
