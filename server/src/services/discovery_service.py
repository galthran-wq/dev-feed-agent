"""Per-user discovery: search new good-first-issues, score them, deliver top matches."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.models.postgres.github_profiles import GithubProfileModel
from src.repositories.github_profiles import GithubProfileRepository
from src.repositories.interest_profiles import InterestProfileRepository
from src.repositories.sent_issues import SentIssueRepository
from src.services import agent_service, notifier
from src.services.github_service import GithubService

logger = structlog.get_logger()


class DiscoveryResult:
    def __init__(self, matches_sent: int, candidates_scanned: int, note: str = "") -> None:
        self.matches_sent = matches_sent
        self.candidates_scanned = candidates_scanned
        self.note = note


async def run_for_user(session: AsyncSession, profile: GithubProfileModel, *, deliver: bool = True) -> DiscoveryResult:
    """Run one discovery pass for a single user.

    ``deliver`` controls Telegram delivery; matches are always recorded for dedup.
    """
    log = logger.bind(user_id=str(profile.user_id))

    if not profile.github_username:
        return DiscoveryResult(0, 0, "no github username configured")

    interest_repo = InterestProfileRepository(session)
    interests = await interest_repo.get_by_user_id(profile.user_id)
    if interests is None or not interests.summary:
        return DiscoveryResult(0, 0, "interest profile not built yet")

    since = profile.last_polled_at or (datetime.now(UTC) - timedelta(hours=24))
    github = GithubService(profile.github_token)
    candidates = await github.search_good_first_issues(since, settings.max_issues_per_poll)

    sent_repo = SentIssueRepository(session)
    unseen_ids = await sent_repo.filter_unseen(profile.user_id, [c.issue_id for c in candidates])
    fresh = [c for c in candidates if c.issue_id in unseen_ids]

    profile_repo = GithubProfileRepository(session)
    await profile_repo.mark_polled(profile)

    if not fresh:
        return DiscoveryResult(0, len(candidates), "no new candidates")

    scored = await agent_service.score_issues(
        interests.summary, interests.languages, interests.topics, interests.keywords, fresh
    )
    relevant = sorted(
        (m for m in scored if m.relevance >= settings.relevance_threshold),
        key=lambda m: m.relevance,
        reverse=True,
    )[: settings.max_matches_per_user]

    matches_sent = 0
    for match in relevant:
        candidate = fresh[match.index]
        await sent_repo.add(
            profile.user_id,
            issue_id=candidate.issue_id,
            repo_full_name=candidate.repo_full_name,
            issue_url=candidate.url,
            title=candidate.title,
            languages=candidate.language,
            stars=candidate.stars,
            relevance=match.relevance,
            reason=match.reason,
        )
        if deliver and profile.telegram_chat_id and settings.telegram_enabled:
            try:
                text = notifier.format_match(
                    repo_full_name=candidate.repo_full_name,
                    title=candidate.title,
                    url=candidate.url,
                    languages=candidate.language,
                    stars=candidate.stars,
                    body=candidate.body,
                    relevance=match.relevance,
                )
                await notifier.send_text(profile.telegram_chat_id, text)
                matches_sent += 1
            except Exception as exc:  # never let a delivery failure abort the pass
                log.warning("telegram_delivery_failed", error=str(exc))

    log.info("discovery_pass_done", scanned=len(candidates), fresh=len(fresh), delivered=matches_sent)
    return DiscoveryResult(matches_sent, len(candidates))
