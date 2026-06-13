"""Thin async wrapper over PyGithub.

PyGithub is synchronous, so every network call is dispatched to a worker thread
via ``asyncio.to_thread`` to avoid blocking the event loop. GitHub's secondary
rate limits surface as HTTP 403/429; those are retried with exponential backoff.
"""

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

import structlog
from github import Auth, Github, GithubException, RateLimitExceededException

logger = structlog.get_logger()

T = TypeVar("T")

# Bound the per-poll API spend so an unauthenticated client (60 req/hour) degrades
# gracefully instead of erroring out mid-scan.
_MAX_TOPIC_LOOKUPS = 60
_MAX_REPO_LOOKUPS = 60
_RETRYABLE_STATUSES = {403, 429}


@dataclass
class RepoSignal:
    full_name: str
    description: str
    language: str | None
    topics: list[str]
    stars: int


@dataclass
class GithubSignals:
    languages: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    repos: list[RepoSignal] = field(default_factory=list)
    starred_count: int = 0
    owned_count: int = 0


@dataclass
class IssueCandidate:
    issue_id: int
    number: int
    title: str
    body: str
    url: str
    repo_full_name: str
    repo_description: str = ""
    language: str | None = None
    stars: int = 0


def _retry(fn: Any, *args: Any, attempts: int = 4, **kwargs: Any) -> Any:
    """Call ``fn`` retrying transient GitHub rate-limit responses with backoff."""
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException as exc:
            last_exc = exc
            logger.warning("github_rate_limited", attempt=attempt, backoff=delay)
        except GithubException as exc:
            if exc.status not in _RETRYABLE_STATUSES:
                raise
            last_exc = exc
            logger.warning("github_secondary_limit", attempt=attempt, status=exc.status, backoff=delay)
        time.sleep(delay)
        delay *= 2
    assert last_exc is not None
    raise last_exc


class GithubService:
    def __init__(self, token: str | None = None):
        self._token = token
        self._github = Github(auth=Auth.Token(token)) if token else Github()

    # --- public async API -------------------------------------------------

    async def collect_signals(self, username: str, max_starred: int = 200) -> GithubSignals:
        return await asyncio.to_thread(self._collect_signals, username, max_starred)

    async def search_good_first_issues(self, since: datetime | None, max_issues: int) -> list[IssueCandidate]:
        return await asyncio.to_thread(self._search_issues, since, max_issues)

    # --- sync implementations (run in a worker thread) --------------------

    def _collect_signals(self, username: str, max_starred: int) -> GithubSignals:
        signals = GithubSignals()
        languages: Counter[str] = Counter()
        topics: Counter[str] = Counter()
        topic_lookups = 0

        user = _retry(self._github.get_user, username)

        starred = _retry(user.get_starred)
        for repo in starred:
            if signals.starred_count >= max_starred:
                break
            signals.starred_count += 1
            repo_topics: list[str] = []
            if topic_lookups < _MAX_TOPIC_LOOKUPS:
                try:
                    repo_topics = _retry(repo.get_topics)
                    topic_lookups += 1
                except GithubException:
                    repo_topics = []
            if repo.language:
                languages[repo.language] += 1
            for topic in repo_topics:
                topics[topic] += 1
            signals.repos.append(
                RepoSignal(
                    full_name=repo.full_name,
                    description=repo.description or "",
                    language=repo.language,
                    topics=repo_topics,
                    stars=repo.stargazers_count,
                )
            )

        try:
            owned = _retry(user.get_repos)
            for repo in owned:
                signals.owned_count += 1
                if repo.language:
                    languages[repo.language] += 2  # own code weighs more than a star
                if signals.owned_count >= 100:
                    break
        except GithubException as exc:
            logger.warning("github_owned_repos_failed", error=str(exc))

        signals.languages = [lang for lang, _ in languages.most_common(12)]
        signals.topics = [topic for topic, _ in topics.most_common(20)]
        return signals

    def _search_issues(self, since: datetime | None, max_issues: int) -> list[IssueCandidate]:
        query = 'label:"good first issue" is:open is:issue no:assignee'
        if since is not None:
            query += f" created:>={since.strftime('%Y-%m-%dT%H:%M:%S+00:00')}"

        results = _retry(self._github.search_issues, query=query, sort="created", order="desc")

        candidates: list[IssueCandidate] = []
        repo_cache: dict[str, RepoSignal] = {}
        repo_lookups = 0

        for issue in results:
            if len(candidates) >= max_issues:
                break
            repo_full_name = _repo_full_name_from_url(issue.repository_url)
            if not repo_full_name:
                continue

            description, language, stars = "", None, 0
            if repo_full_name in repo_cache:
                cached = repo_cache[repo_full_name]
                description, language, stars = cached.description, cached.language, cached.stars
            elif repo_lookups < _MAX_REPO_LOOKUPS:
                try:
                    repo = _retry(self._github.get_repo, repo_full_name)
                    repo_lookups += 1
                    description = repo.description or ""
                    language = repo.language
                    stars = repo.stargazers_count
                    repo_cache[repo_full_name] = RepoSignal(
                        full_name=repo_full_name,
                        description=description,
                        language=language,
                        topics=[],
                        stars=stars,
                    )
                except GithubException as exc:
                    logger.warning("github_repo_lookup_failed", repo=repo_full_name, error=str(exc))

            candidates.append(
                IssueCandidate(
                    issue_id=issue.id,
                    number=issue.number,
                    title=issue.title,
                    body=(issue.body or "")[:1500],
                    url=issue.html_url,
                    repo_full_name=repo_full_name,
                    repo_description=description,
                    language=language,
                    stars=stars,
                )
            )

        return candidates


def _repo_full_name_from_url(repository_url: str | None) -> str | None:
    """Extract ``owner/name`` from an API URL like .../repos/owner/name."""
    if not repository_url:
        return None
    marker = "/repos/"
    idx = repository_url.find(marker)
    if idx == -1:
        return None
    return repository_url[idx + len(marker) :]
