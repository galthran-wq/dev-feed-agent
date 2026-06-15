"""Minimal async GitHub REST client used by the agent's GitHub tools.

Scoped to a single user's OAuth token (or unauthenticated with lower rate limits).
Returns plain dicts/lists — the tools shape them into compact text for the model.
"""

import asyncio
import base64
import re
from typing import Any
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger()

_API = "https://api.github.com"
_MANIFESTS = ("pyproject.toml", "requirements.txt", "package.json")
# owner/name — reject anything that could traverse to another API path.
_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# GitHub forbids concurrent requests for a single user and aggressively secondary-rate-limits
# (403) bursts to the low-quota Search API. The feed fan-out runs many gatherers in parallel,
# each searching — so serialize search across the whole process to avoid the 403 storm.
_SEARCH_GATE = asyncio.Semaphore(1)


def _safe_full_name(full_name: str) -> str:
    if not _FULL_NAME_RE.match(full_name):
        raise ValueError(f"Invalid repository name: {full_name!r}")
    return full_name


class GithubClient:
    def __init__(self, token: str | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers = headers

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=20.0, headers=self._headers) as client:
            resp = await client.get(f"{_API}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def _search(self, path: str, params: dict[str, Any]) -> Any:
        """Search endpoints, serialized across the process and retried on secondary rate limits
        (403/429) so parallel feed gatherers don't trip GitHub's burst protection."""
        async with _SEARCH_GATE:
            for attempt in range(3):
                try:
                    return await self._get(path, params)
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in (403, 429) and attempt < 2:
                        retry_after = exc.response.headers.get("retry-after")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 * (attempt + 1)
                        logger.warning("github_search_rate_limited", status=status, delay=delay, attempt=attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise
        return None  # unreachable; loop either returns or raises

    async def list_owned_repos(self, limit: int = 50) -> list[dict[str, Any]]:
        repos = await self._get("/user/repos", {"per_page": min(limit, 100), "sort": "pushed", "affiliation": "owner"})
        return [_repo_summary(r) for r in repos[:limit]]

    async def list_starred(self, username: str, limit: int = 50) -> list[dict[str, Any]]:
        repos = await self._get(f"/users/{username}/starred", {"per_page": min(limit, 100)})
        return [_repo_summary(r) for r in repos[:limit]]

    async def get_repo(self, full_name: str) -> dict[str, Any]:
        return _repo_summary(await self._get(f"/repos/{_safe_full_name(full_name)}"))

    async def get_manifest(self, full_name: str, filename: str) -> str | None:
        """Fetch and decode a manifest file's text, or None if it doesn't exist."""
        path = f"/repos/{_safe_full_name(full_name)}/contents/{quote(filename)}"
        try:
            data = await self._get(path)
        except httpx.HTTPStatusError:
            return None
        content = data.get("content")
        if not content or data.get("encoding") != "base64":
            return None
        return base64.b64decode(content).decode("utf-8", errors="replace")

    async def find_manifests(self, full_name: str) -> dict[str, str]:
        """Return {filename: content} for the manifests present at the repo root."""
        found: dict[str, str] = {}
        for name in _MANIFESTS:
            text = await self.get_manifest(full_name, name)
            if text is not None:
                found[name] = text
        return found

    async def search_issues(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        data = await self._search("/search/issues", {"q": query, "sort": "created", "order": "desc", "per_page": limit})
        return [_issue_summary(i) for i in data.get("items", [])[:limit]]

    async def search_repos(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._search(
            "/search/repositories", {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
        )
        return [_repo_summary(r) for r in data.get("items", [])[:limit]]


def _repo_summary(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": r.get("full_name"),
        "description": (r.get("description") or "")[:200],
        "language": r.get("language"),
        "topics": r.get("topics", []),
        "stars": r.get("stargazers_count", 0),
        "url": r.get("html_url"),
        "pushed_at": r.get("pushed_at"),
    }


def _issue_summary(i: dict[str, Any]) -> dict[str, Any]:
    repo_url = i.get("repository_url", "")
    full_name = repo_url.split("/repos/", 1)[-1] if "/repos/" in repo_url else ""
    return {
        "id": str(i.get("id")),
        "title": i.get("title"),
        "url": i.get("html_url"),
        "repo_full_name": full_name,
        "labels": [lbl.get("name") for lbl in i.get("labels", [])],
        "body": (i.get("body") or "")[:500],
        "created_at": i.get("created_at"),
    }
