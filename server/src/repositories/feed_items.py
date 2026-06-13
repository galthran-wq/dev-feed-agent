from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.feed_items import FeedItemModel


class FeedItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def filter_unseen(self, user_id: UUID, keys: list[tuple[str, str]]) -> set[tuple[str, str]]:
        """Given ``(source, external_id)`` keys, return the subset not yet delivered to the user."""
        if not keys:
            return set()
        sources = {s for s, _ in keys}
        result = await self.session.execute(
            select(FeedItemModel.source, FeedItemModel.external_id).where(
                FeedItemModel.user_id == user_id,
                FeedItemModel.source.in_(sources),
            )
        )
        seen = {(row[0], row[1]) for row in result.all()}
        return {k for k in keys if k not in seen}

    async def add(
        self,
        user_id: UUID,
        *,
        source: str,
        item_type: str,
        external_id: str,
        url: str,
        title: str,
        summary: str | None = None,
        reason: str | None = None,
        bucket: str = "exploit",
    ) -> FeedItemModel:
        item = FeedItemModel(
            user_id=user_id,
            source=source,
            item_type=item_type,
            external_id=external_id,
            url=url,
            title=title,
            summary=summary,
            reason=reason,
            bucket=bucket,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def count(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(FeedItemModel).where(FeedItemModel.user_id == user_id)
        )
        return int(result.scalar_one())

    async def list_recent(self, user_id: UUID, limit: int = 50) -> list[FeedItemModel]:
        result = await self.session.execute(
            select(FeedItemModel)
            .where(FeedItemModel.user_id == user_id)
            .order_by(FeedItemModel.delivered_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
