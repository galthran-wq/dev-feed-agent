import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class AgentMessageModel(Base):
    """Durable agent memory: one row per run, replayed so chat and the scheduled feed share one history."""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data: Mapped[str] = mapped_column(Text)  # JSON array of ModelMessage
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
