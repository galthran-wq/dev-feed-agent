from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.profiles import PROFILE_SECTIONS, ProfileModel


def render_markdown(sections: dict[str, str]) -> str:
    """Render the sectioned profile to a stable markdown document (fixed section order)."""
    parts: list[str] = []
    for name in PROFILE_SECTIONS:
        body = (sections.get(name) or "").strip()
        parts.append(f"## {name}\n\n{body or '_(empty)_'}")
    return "\n\n".join(parts)


class ProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> ProfileModel | None:
        # populate_existing: a profile can be (re)built by a sub-agent on a *different* session,
        # so always refresh from the DB rather than returning a stale identity-map copy. Safe
        # because profile writes (set_section) commit immediately — no pending in-session edits.
        result = await self.session.execute(
            select(ProfileModel).where(ProfileModel.user_id == user_id).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: UUID) -> ProfileModel:
        profile = await self.get_by_user_id(user_id)
        if profile is not None:
            return profile
        profile = ProfileModel(user_id=user_id, sections={})
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def get_markdown(self, user_id: UUID) -> str:
        profile = await self.get_by_user_id(user_id)
        return render_markdown(profile.sections if profile else {})

    async def is_built(self, user_id: UUID) -> bool:
        profile = await self.get_by_user_id(user_id)
        return profile is not None and profile.built_at is not None

    async def set_section(self, user_id: UUID, section: str, content: str) -> ProfileModel:
        profile = await self.get_or_create(user_id)
        # Reassign the whole dict so SQLAlchemy detects the mutation on the JSON column.
        sections = dict(profile.sections)
        sections[section] = content
        profile.sections = sections
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def mark_built(self, user_id: UUID) -> None:
        """Stamp the profile as built."""
        profile = await self.get_or_create(user_id)
        profile.built_at = datetime.now(UTC)
        await self.session.commit()

    async def replace_all(self, user_id: UUID, sections: dict[str, str]) -> ProfileModel:
        """Replace the whole profile and stamp built_at."""
        profile = await self.get_or_create(user_id)
        profile.sections = dict(sections)
        profile.built_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
