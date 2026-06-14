from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    # Every Mapped[datetime] column is timezone-aware (timestamptz). The codebase writes
    # aware datetime.now(UTC); a naive column makes asyncpg reject those on Postgres
    # ("can't subtract offset-naive and offset-aware datetimes").
    type_annotation_map = {datetime: DateTime(timezone=True)}


postgres_engine = create_async_engine(
    settings.postgres_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)
AsyncSessionLocal = async_sessionmaker(postgres_engine, class_=AsyncSession, expire_on_commit=False)


async def get_postgres_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
