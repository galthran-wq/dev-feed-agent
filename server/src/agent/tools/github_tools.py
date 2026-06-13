"""Tools that read a user's GitHub footprint — the raw material for the profile."""

import json

import structlog
from pydantic_ai import RunContext
from src.agent.dependency_parser import parse_dependencies
from src.agent.deps import AgentDeps
from src.agent.github_client import GithubClient

logger = structlog.get_logger()


def _client(ctx: RunContext[AgentDeps]) -> GithubClient:
    return GithubClient(ctx.deps.github_token)


async def list_my_repos(ctx: RunContext[AgentDeps], limit: int = 50) -> str:
    """List the repositories the user owns (name, language, stars, topics, description).

    Use this to understand what the developer actually builds.
    """
    try:
        repos = await _client(ctx).list_owned_repos(limit=limit)
    except Exception as exc:
        return f"Could not list repos: {exc}"
    return json.dumps(repos, ensure_ascii=False)


async def list_my_starred(ctx: RunContext[AgentDeps], limit: int = 40) -> str:
    """List repositories the user has starred — a signal of what they find interesting."""
    if not ctx.deps.github_username:
        return "No GitHub username on file."
    try:
        repos = await _client(ctx).list_starred(ctx.deps.github_username, limit=limit)
    except Exception as exc:
        return f"Could not list starred repos: {exc}"
    return json.dumps(repos, ensure_ascii=False)


async def scan_repo_dependencies(ctx: RunContext[AgentDeps], repo_full_name: str) -> str:
    """Read the dependency manifests of a repo (pyproject.toml / requirements.txt /
    package.json) and return the package names used. Great for inferring real stack."""
    try:
        manifests = await _client(ctx).find_manifests(repo_full_name)
    except Exception as exc:
        return f"Could not scan {repo_full_name}: {exc}"
    if not manifests:
        return f"No recognized manifests at the root of {repo_full_name}."
    result = {fname: parse_dependencies(fname, text) for fname, text in manifests.items()}
    return json.dumps(result, ensure_ascii=False)


GITHUB_TOOLS = [list_my_repos, list_my_starred, scan_repo_dependencies]
