import uuid
from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    password_hash: Mapped[str | None] = mapped_column(String, default=None)
    is_verified: Mapped[bool] = mapped_column(default=False)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    # --- GitHub OAuth identity (populated on "Connect via GitHub") ---
    github_id: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    github_username: Mapped[str | None] = mapped_column(String, default=None)
    # OAuth access token, stored as-is; treat as a secret. Used for GitHub API calls.
    github_access_token: Mapped[str | None] = mapped_column(String, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String, default=None)
