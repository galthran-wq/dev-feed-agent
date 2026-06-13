"""Shared interest-profile operations used by both the web API and the Telegram bot."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.interest_profiles import InterestProfileModel
from src.repositories.chat_messages import ChatMessageRepository
from src.repositories.interest_profiles import InterestProfileRepository
from src.services import agent_service
from src.services.agent_service import InterestProfileOutput, RefineOutput
from src.services.github_service import GithubService

logger = structlog.get_logger()


async def rebuild_profile(
    session: AsyncSession, user_id: UUID, username: str, token: str | None
) -> tuple[InterestProfileModel, int]:
    """Fetch GitHub activity and (re)build the stored interest profile."""
    github = GithubService(token)
    signals = await github.collect_signals(username)
    inferred = await agent_service.build_interest_profile(signals)

    repo = InterestProfileRepository(session)
    stored = await repo.upsert(
        user_id,
        summary=inferred.summary,
        languages=inferred.languages,
        topics=inferred.topics,
        keywords=inferred.keywords,
    )
    return stored, len(signals.repos)


async def refine_for_user(session: AsyncSession, user_id: UUID, text: str) -> RefineOutput:
    """Apply a chat message to the user's interest profile and persist the exchange."""
    interest_repo = InterestProfileRepository(session)
    chat_repo = ChatMessageRepository(session)

    stored = await interest_repo.get_by_user_id(user_id)
    current = InterestProfileOutput(
        summary=stored.summary if stored else "",
        languages=stored.languages if stored else [],
        topics=stored.topics if stored else [],
        keywords=stored.keywords if stored else [],
    )
    history = [(m.role, m.content) for m in await chat_repo.list_recent(user_id, limit=20)]

    result = await agent_service.refine_interests(current, history, text)

    await chat_repo.add(user_id, "user", text)
    await chat_repo.add(user_id, "assistant", result.reply)
    await interest_repo.upsert(
        user_id,
        summary=result.summary,
        languages=result.languages,
        topics=result.topics,
        keywords=result.keywords,
    )
    return result
