import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class AgentMessageModel(Base):
    """Durable agent conversation memory.

    Each row is one agent run's *new* messages, serialized as a JSON array of
    pydantic-ai ``ModelMessage`` objects (user turn, tool calls, tool results,
    assistant reply). Rows are concatenated chronologically and replayed via
    ``message_history=`` so tool context survives across turns — and so the chat
    and the scheduled feed share one memory.
    """

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data: Mapped[str] = mapped_column(Text)  # JSON array of ModelMessage for one run
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
