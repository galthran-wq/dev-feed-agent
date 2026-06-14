import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

# Fixed, ordered sections; markdown is rendered from this list.
PROFILE_SECTIONS: list[str] = [
    "Summary",
    "Languages & stacks",
    "Domains & topics",
    "Notable repos & dependencies",
    "Preferences",
    "Current focus & deep-dives",
]


class ProfileModel(Base):
    """The agent's self-managed user profile. Stored as a section map so one section can be patched in isolation."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    sections: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    built_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
