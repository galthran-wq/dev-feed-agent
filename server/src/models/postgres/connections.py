import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


def _link_code() -> str:
    return secrets.token_urlsafe(12)


class ConnectionModel(Base):
    """Per-user delivery target + feed scheduling. GitHub identity lives on ``users`` (the sign-in identity)."""

    __tablename__ = "connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    telegram_chat_id: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    # One-time code in the /start deep link; single-use to guard against chat hijack if the URL leaks.
    telegram_link_code: Mapped[str] = mapped_column(String, unique=True, default=_link_code)

    feed_enabled: Mapped[bool] = mapped_column(default=True)
    last_feed_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
