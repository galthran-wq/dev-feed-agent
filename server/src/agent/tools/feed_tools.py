"""Tools that search GitHub for fresh feed candidates (issues, help-wanted, repos).

The other sources (HuggingFace, Hacker News, arXiv, Reddit) reach the agent as MCP
toolsets, so GitHub is the only source that needs hand-written search tools here.
"""

import json
from datetime import UTC, datetime, timedelta

import structlog
from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.agent.github_client import GithubClient

logger = structlog.get_logger()


def _client(ctx: RunContext[AgentDeps]) -> GithubClient:
    return GithubClient(ctx.deps.github_token)


async def find_github_issues(
    ctx: RunContext[AgentDeps],
    label: str = "good first issue",
    language: str = "",
    keywords: str = "",
    days: int = 7,
    limit: int = 30,
) -> str:
    """Search open, unassigned issues with a given label (e.g. "good first issue",
    "help wanted"), optionally filtered by language/keywords and created within the
    last ``days``. Returns id, title, url, repo, labels, body snippet."""
    since = (datetime.now(UTC) - timedelta(days=max(days, 1))).strftime("%Y-%m-%d")
    parts = [f'label:"{label}"', "is:open", "is:issue", "no:assignee", f"created:>={since}"]
    if language:
        parts.append(f"language:{language}")
    if keywords:
        parts.append(keywords)
    try:
        issues = await _client(ctx).search_issues(" ".join(parts), limit=limit)
    except Exception as exc:
        return f"Issue search failed: {exc}"
    return json.dumps(issues, ensure_ascii=False)


async def search_github_repositories(ctx: RunContext[AgentDeps], query: str, limit: int = 20) -> str:
    """Search repositories by a free-form query (e.g. "topic:rust embedded stars:>100").
    Useful for surfacing fresh or trending projects in a domain."""
    try:
        repos = await _client(ctx).search_repos(query, limit=limit)
    except Exception as exc:
        return f"Repo search failed: {exc}"
    return json.dumps(repos, ensure_ascii=False)


FEED_TOOLS = [find_github_issues, search_github_repositories]
