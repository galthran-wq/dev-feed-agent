from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.interest_profiles import InterestProfileModel


class InterestProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> InterestProfileModel | None:
        result = await self.session.execute(select(InterestProfileModel).where(InterestProfileModel.user_id == user_id))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: UUID,
        *,
        summary: str,
        languages: list[str],
        topics: list[str],
        keywords: list[str],
    ) -> InterestProfileModel:
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = InterestProfileModel(user_id=user_id)
            self.session.add(profile)
        profile.summary = summary
        profile.languages = languages
        profile.topics = topics
        profile.keywords = keywords
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
