import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class MemoryModel(Base):
    """A specific, local fact the agent chooses to remember about a user.

    Distinct from the **profile** (general, persistent, high-level facts the agent
    rewrites section by section): a memory is a narrow, often time-stamped note —
    "on 2026-06-13 they declined contributing to that JS project", "asked about CRDTs
    once". The agent manages these via CRUD tools and reads them alongside the profile.
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
