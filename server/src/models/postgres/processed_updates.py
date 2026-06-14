from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class ProcessedUpdateModel(Base):
    """Telegram ``update_id``s we've already handled.

    Telegram delivers webhook updates at-least-once (it re-sends until it gets a 2XX, and
    can redeliver across restarts). Agent runs have non-idempotent side effects (sent
    messages, recorded feed items), so we dedup on ``update_id`` before processing.
    """

    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
