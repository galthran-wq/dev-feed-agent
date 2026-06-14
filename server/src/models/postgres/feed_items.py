import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class FeedItemModel(Base):
    """An item surfaced to a user. Doubles as the dedup ledger; ``external_id`` is source-scoped and free-form."""

    __tablename__ = "feed_items"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id", name="uq_feed_item_per_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    source: Mapped[str] = mapped_column(String(32))  # github | hf | hackernews | arxiv | reddit
    item_type: Mapped[str] = mapped_column(String(32))  # repo | issue | help_wanted | paper | model | post | story
    external_id: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    reason: Mapped[str | None] = mapped_column(Text, default=None)
    bucket: Mapped[str] = mapped_column(String(16), default="exploit")  # exploit | explore
    status: Mapped[str] = mapped_column(String(16), default="delivered")  # delivered | saved | dismissed

    delivered_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
