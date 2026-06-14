from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.processed_updates import ProcessedUpdateModel


class ProcessedUpdateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seen_or_mark(self, update_id: int) -> bool:
        """Atomically check-and-mark a Telegram ``update_id``.

        Returns True if it was already processed (caller should drop the update), or False
        if this call is the first to claim it (caller should process it). The PK + commit
        makes it race-safe: a concurrent duplicate hits the unique violation and is treated
        as already-seen.
        """
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
