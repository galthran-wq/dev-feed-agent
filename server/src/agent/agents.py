"""Agent factories for dev-feed-agent.

A fresh ``Agent`` is built per run (cheap — no network at construction) so there is no
shared mutable state across concurrent requests; MCP connections open lazily inside
``async with agent``. The model is OpenRouter via its OpenAI-compatible endpoint.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from src.agent.deps import AgentDeps
from src.agent.mcp import build_mcp_servers
from src.agent.tools import CHAT_TOOLS, PROFILE_TOOLS
from src.core.config import settings

_PROMPTS = Path(__file__).parent / "prompts"


@lru_cache
def _prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _model(name: str) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)
    return OpenAIChatModel(name, provider=provider)


class CuratedItem(BaseModel):
    source: str = Field(description="github | hf | hackernews | arxiv | reddit")
    item_type: str = Field(description="repo | issue | help_wanted | paper | model | post | story")
    external_id: str = Field(description="source-scoped stable id (repo full name, arXiv id, HN id, ...)")
    url: str
    title: str
    summary: str = ""
    reason: str
    bucket: str = Field(description="exploit | explore")


class FeedOutput(BaseModel):
    items: list[CuratedItem] = Field(default_factory=list)


def make_profile_agent() -> Agent[AgentDeps, str]:
    """Explore-style sub-agent: walks GitHub and writes the sectioned profile."""
    return Agent(
        _model(settings.profile_model),
        deps_type=AgentDeps,
        system_prompt=_prompt("profile_builder.md"),
        tools=PROFILE_TOOLS,
    )


def make_chat_agent() -> Agent[AgentDeps, str]:
    """Conversational agent (Telegram): memory-aware, can call all tools + MCP sources."""
    return Agent(
        _model(settings.agent_model),
        deps_type=AgentDeps,
        system_prompt=_prompt("chat.md"),
        tools=CHAT_TOOLS,
        toolsets=build_mcp_servers(),
    )


def make_curator_agent() -> Agent[AgentDeps, FeedOutput]:
    """Feed curator: gathers candidates across sources and returns scored, bucketed items."""
    return Agent(
        _model(settings.agent_model),
        deps_type=AgentDeps,
        output_type=FeedOutput,
        system_prompt=_prompt("feed_curator.md"),
        tools=CHAT_TOOLS,
        toolsets=build_mcp_servers(),
    )
