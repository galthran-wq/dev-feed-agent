"""pydantic-ai agent powering interest inference, chat refinement, and issue scoring.

The model is reached through OpenRouter's OpenAI-compatible endpoint. There are no
embeddings: relevance is decided by the LLM reasoning over the interest profile.
"""

import json

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model
from src.core.config import settings
from src.core.exceptions import AppError
from src.services.github_service import GithubSignals, IssueCandidate

logger = structlog.get_logger()


class InterestProfileOutput(BaseModel):
    summary: str = Field(description="2-4 sentence summary of the developer's interests")
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, description="Free-form interest keywords")


class RefineOutput(InterestProfileOutput):
    reply: str = Field(description="Short conversational reply to the user")


class ScoredIssue(BaseModel):
    index: int
    relevance: float = Field(ge=0.0, le=1.0)
    reason: str


class ScoringOutput(BaseModel):
    matches: list[ScoredIssue] = Field(default_factory=list)


def _build_model() -> Model:
    """Construct an OpenRouter-backed model (OpenAI-compatible API)."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)
    return OpenAIChatModel(settings.agent_model, provider=provider)


def _require_agent() -> None:
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")


_PROFILE_PROMPT = (
    "You profile a software developer from their GitHub activity. Infer the languages, "
    "topics, and concrete keywords that describe what they like to build and contribute to. "
    "Write a concise, specific summary. Prefer signal from owned repositories and frequently "
    "recurring topics over one-off stars."
)

_REFINE_PROMPT = (
    "You maintain a developer's interest profile used to recommend good-first-issues. "
    "Given the current profile, recent conversation, and a new user message, return an updated "
    "profile and a short friendly reply confirming what changed. Only adjust fields the user "
    "is actually asking to change; keep everything else stable."
)

_SCORING_PROMPT = (
    "You match open-source 'good first issue' tickets to a developer's interests. For each "
    "candidate, assign a relevance score from 0.0 (irrelevant) to 1.0 (an excellent fit) and a "
    "one-sentence reason. Weigh language overlap, topic/domain fit, and how approachable the issue "
    "looks for a newcomer. Only return candidates scoring 0.4 or higher."
)


# Agents are built lazily so importing this module never requires a configured key.
_profile_agent: Agent[None, InterestProfileOutput] | None = None
_refine_agent: Agent[None, RefineOutput] | None = None
_scoring_agent: Agent[None, ScoringOutput] | None = None


def _get_profile_agent() -> Agent[None, InterestProfileOutput]:
    global _profile_agent
    if _profile_agent is None:
        _profile_agent = Agent(_build_model(), output_type=InterestProfileOutput, system_prompt=_PROFILE_PROMPT)
    return _profile_agent


def _get_refine_agent() -> Agent[None, RefineOutput]:
    global _refine_agent
    if _refine_agent is None:
        _refine_agent = Agent(_build_model(), output_type=RefineOutput, system_prompt=_REFINE_PROMPT)
    return _refine_agent


def _get_scoring_agent() -> Agent[None, ScoringOutput]:
    global _scoring_agent
    if _scoring_agent is None:
        _scoring_agent = Agent(_build_model(), output_type=ScoringOutput, system_prompt=_SCORING_PROMPT)
    return _scoring_agent


async def build_interest_profile(signals: GithubSignals) -> InterestProfileOutput:
    _require_agent()
    repo_lines = [
        f"- {r.full_name} [{r.language or 'n/a'}] ({r.stars}★): {r.description[:160]}"
        + (f" topics={','.join(r.topics)}" if r.topics else "")
        for r in signals.repos[:80]
    ]
    prompt = (
        f"Aggregated languages: {', '.join(signals.languages) or 'none'}\n"
        f"Aggregated topics: {', '.join(signals.topics) or 'none'}\n"
        f"Starred repos scanned: {signals.starred_count}, owned repos: {signals.owned_count}\n\n"
        f"Repositories:\n" + "\n".join(repo_lines)
    )
    result = await _get_profile_agent().run(prompt)
    return result.output


async def refine_interests(
    current: InterestProfileOutput, history: list[tuple[str, str]], user_message: str
) -> RefineOutput:
    _require_agent()
    convo = "\n".join(f"{role}: {content}" for role, content in history[-10:])
    prompt = (
        f"Current profile:\n{current.model_dump_json(indent=2)}\n\n"
        f"Recent conversation:\n{convo or '(none)'}\n\n"
        f"New user message: {user_message}"
    )
    result = await _get_refine_agent().run(prompt)
    return result.output


async def score_issues(
    summary: str,
    languages: list[str],
    topics: list[str],
    keywords: list[str],
    candidates: list[IssueCandidate],
) -> list[ScoredIssue]:
    _require_agent()
    if not candidates:
        return []
    profile_blob = json.dumps(
        {"summary": summary, "languages": languages, "topics": topics, "keywords": keywords},
        ensure_ascii=False,
    )
    issue_lines = [
        f"[{i}] {c.repo_full_name} [{c.language or 'n/a'}] ({c.stars}★) — {c.title}\n"
        f"     repo: {c.repo_description[:160]}\n"
        f"     issue: {c.body[:280]}"
        for i, c in enumerate(candidates)
    ]
    prompt = f"Developer profile:\n{profile_blob}\n\nCandidate issues:\n" + "\n".join(issue_lines)
    result = await _get_scoring_agent().run(prompt)
    # Guard against out-of-range indices hallucinated by the model.
    return [m for m in result.output.matches if 0 <= m.index < len(candidates)]
