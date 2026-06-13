import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


def _link_code() -> str:
    return secrets.token_urlsafe(12)


class GithubProfileModel(Base):
    """Per-user connection settings: GitHub identity + Telegram delivery target."""

    __tablename__ = "github_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    github_username: Mapped[str | None] = mapped_column(String, default=None)
    # Stored as-is; treat as a secret. Optional — a token lifts rate limits and
    # enables private contribution signals, but public discovery works without it.
    github_token: Mapped[str | None] = mapped_column(String, default=None)

    # Telegram chat the bot delivers matches to. Linked via the bot's /start flow.
    telegram_chat_id: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    # One-time code embedded in the Telegram deep link to bind a chat to this user.
    telegram_link_code: Mapped[str] = mapped_column(String, unique=True, default=_link_code)

    poll_enabled: Mapped[bool] = mapped_column(default=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
