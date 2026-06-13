from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.sent_issues import SentIssueModel


class SentIssueRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists(self, user_id: UUID, issue_id: int) -> bool:
        result = await self.session.execute(
            select(SentIssueModel.id).where(SentIssueModel.user_id == user_id, SentIssueModel.issue_id == issue_id)
        )
        return result.scalar_one_or_none() is not None

    async def filter_unseen(self, user_id: UUID, issue_ids: list[int]) -> set[int]:
        """Return the subset of issue_ids that have NOT been sent to this user."""
        if not issue_ids:
            return set()
        result = await self.session.execute(
            select(SentIssueModel.issue_id).where(
                SentIssueModel.user_id == user_id, SentIssueModel.issue_id.in_(issue_ids)
            )
        )
        seen = set(result.scalars().all())
        return {iid for iid in issue_ids if iid not in seen}

    async def add(
        self,
        user_id: UUID,
        *,
        issue_id: int,
        repo_full_name: str,
        issue_url: str,
        title: str,
        languages: str | None,
        stars: int,
        relevance: float,
        reason: str | None,
    ) -> SentIssueModel:
        record = SentIssueModel(
            user_id=user_id,
            issue_id=issue_id,
            repo_full_name=repo_full_name,
            issue_url=issue_url,
            title=title,
            languages=languages,
            stars=stars,
            relevance=relevance,
            reason=reason,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_recent(self, user_id: UUID, limit: int = 20) -> list[SentIssueModel]:
        result = await self.session.execute(
            select(SentIssueModel)
            .where(SentIssueModel.user_id == user_id)
            .order_by(SentIssueModel.sent_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
