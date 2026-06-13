import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class InterestProfileModel(Base):
    """The agent-maintained interest profile (durable per-user "memory").

    Built from GitHub activity and refined through chat. This is what the
    discovery agent scores candidate issues against.
    """

    __tablename__ = "interest_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    summary: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
