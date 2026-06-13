import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

# Canonical, fixed sections of the interest profile. The agent fills/updates them
# section-by-section; the document is rendered to markdown from this ordered list.
PROFILE_SECTIONS: list[str] = [
    "Summary",
    "Languages & stacks",
    "Domains & topics",
    "Notable repos & dependencies",
    "Preferences",
    "Current focus & deep-dives",
]


class ProfileModel(Base):
    """The agent's self-managed memory about a user: a sectioned markdown profile.

    Stored as a ``{section_name: content}`` map so a single section can be patched
    atomically without rewriting the whole document. Rendered to markdown on read.
    """

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    sections: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    built_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
