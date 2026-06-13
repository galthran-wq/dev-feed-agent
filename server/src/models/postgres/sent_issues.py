import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class SentIssueModel(Base):
    """Deduplication + history: every issue delivered to a user, once."""

    __tablename__ = "sent_issues"
    __table_args__ = (UniqueConstraint("user_id", "issue_id", name="uq_sent_issue_per_user"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # GitHub's numeric issue id (stable, unlike the per-repo issue number).
    issue_id: Mapped[int] = mapped_column(BigInteger)
    repo_full_name: Mapped[str] = mapped_column(String)
    issue_url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(Text)
    languages: Mapped[str | None] = mapped_column(String, default=None)
    stars: Mapped[int] = mapped_column(default=0)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    sent_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
