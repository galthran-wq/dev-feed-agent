from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.github_profiles import GithubProfileModel


class GithubProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> GithubProfileModel | None:
        result = await self.session.execute(select(GithubProfileModel).where(GithubProfileModel.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_chat_id(self, chat_id: str) -> GithubProfileModel | None:
        result = await self.session.execute(
            select(GithubProfileModel).where(GithubProfileModel.telegram_chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_by_link_code(self, code: str) -> GithubProfileModel | None:
        result = await self.session.execute(
            select(GithubProfileModel).where(GithubProfileModel.telegram_link_code == code)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: UUID) -> GithubProfileModel:
        profile = await self.get_by_user_id(user_id)
        if profile is not None:
            return profile
        profile = GithubProfileModel(user_id=user_id)
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_settings(
        self,
        user_id: UUID,
        *,
        github_username: str | None = None,
        github_token: str | None = None,
        poll_enabled: bool | None = None,
    ) -> GithubProfileModel:
        profile = await self.get_or_create(user_id)
        if github_username is not None:
            profile.github_username = github_username.strip() or None
        if github_token is not None:
            # Empty string clears the stored token.
            profile.github_token = github_token.strip() or None
        if poll_enabled is not None:
            profile.poll_enabled = poll_enabled
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def link_telegram(self, code: str, chat_id: str) -> GithubProfileModel | None:
        profile = await self.get_by_link_code(code)
        if profile is None:
            return None
        profile.telegram_chat_id = chat_id
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def mark_polled(self, profile: GithubProfileModel) -> None:
        profile.last_polled_at = datetime.now(UTC)
        await self.session.commit()

    async def list_pollable(self) -> list[GithubProfileModel]:
        """Profiles eligible for the scheduled poll: enabled, with a username and a delivery target."""
        result = await self.session.execute(
            select(GithubProfileModel).where(
                GithubProfileModel.poll_enabled.is_(True),
                GithubProfileModel.github_username.is_not(None),
                GithubProfileModel.telegram_chat_id.is_not(None),
            )
        )
        return list(result.scalars().all())
