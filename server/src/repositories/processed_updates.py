from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.processed_updates import ProcessedUpdateModel


class ProcessedUpdateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seen_or_mark(self, update_id: int) -> bool:
        """Check-and-mark an ``update_id``. True = already seen (drop it); False = first to
        claim it (process it). Race-safe: a concurrent duplicate hits the PK unique violation → seen."""
        existing = await self.session.get(ProcessedUpdateModel, update_id)
        if existing is not None:
            return True
        self.session.add(ProcessedUpdateModel(update_id=update_id))
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return True
        return False
