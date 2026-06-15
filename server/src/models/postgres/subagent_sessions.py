import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class SubagentSessionModel(Base):
    """One resumable sub-agent conversation: its full pydantic-ai trace, keyed by id and owned
    by a user. The main agent spawns these to keep its own context lean — only a short result
    string returns to it, while the heavy investigation lives here and can be resumed by id."""

    __tablename__ = "subagent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64))
    data: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of ModelMessage
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Composite (user_id leftmost) serves both per-user and per-(user,kind) lookups.
    __table_args__ = (Index("ix_subagent_sessions_user_kind", "user_id", "kind"),)
