from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories.processed_updates import ProcessedUpdateRepository


async def test_seen_or_mark_dedups(db_session: AsyncSession) -> None:
    repo = ProcessedUpdateRepository(db_session)
    # First sighting claims it (False = not seen before → process it).
    assert await repo.seen_or_mark(100) is False
    # Repeat is recognized as already-processed.
    assert await repo.seen_or_mark(100) is True
    # A different update is independent.
    assert await repo.seen_or_mark(101) is False
