from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class ProcessedUpdateModel(Base):
    """Dedup ledger of Telegram ``update_id``s. Webhook delivery is at-least-once and agent
    runs aren't idempotent (sent messages, recorded items), so we dedup before processing.
    Tradeoffs: mark-before-process → at-most-once on a mid-handle crash; grows without TTL (prune later)."""

    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
