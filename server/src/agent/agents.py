"""Agent factories for dev-feed-agent.

A fresh ``Agent`` is built per run (cheap — no network at construction) so there is no
shared mutable state across concurrent requests; MCP connections open lazily inside
``async with agent``. The model is OpenRouter via its OpenAI-compatible endpoint.

``make_chat_agent`` is async because it *probes* its MCP sources first and wires in only
the reachable ones — a single dead source must not abort the whole run (see ``mcp.py``).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from src.agent.deps import AgentDeps
from src.agent.mcp import reachable_mcp_servers
from src.agent.tools import CHAT_TOOLS, PROFILE_TOOLS
from src.core.config import settings

_PROMPTS = Path(__file__).parent / "prompts"


@lru_cache
def _prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _model(name: str) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)
    return OpenAIChatModel(name, provider=provider)


def make_profile_agent() -> Agent[AgentDeps, str]:
    """Explore-style sub-agent: walks GitHub and writes the sectioned profile."""
    return Agent(
        _model(settings.profile_model),
        deps_type=AgentDeps,
        system_prompt=_prompt("profile_builder.md"),
        tools=PROFILE_TOOLS,
    )


def make_summarizer_agent() -> Agent[None, str]:
    """No-tools agent used by /compact to summarize prior history into a short note."""
    return Agent(
        _model(settings.agent_model),
        system_prompt=(
            "You compact a conversation for your future self. Given the prior messages, write a "
            "tight note capturing durable facts about the user, their stated preferences, current "
            "focus, and what's already been shown. Be concise; omit small talk. Do not call tools."
        ),
    )


async def make_chat_agent() -> Agent[AgentDeps, str]:
    """The one memory-aware agent: handles Telegram chat AND assembles the scheduled
    feed (driven by a synthetic turn). Free-form text out; it records what it surfaces
    via the record_feed_items tool. Can call all tools + MCP sources.

    Probes the configured MCP sources first and wires in only the reachable ones, so an
    unreachable source is skipped (logged) rather than aborting the run.
    """
    return Agent(
        _model(settings.agent_model),
        deps_type=AgentDeps,
        system_prompt=_prompt("chat.md"),
        tools=CHAT_TOOLS,
        toolsets=await reachable_mcp_servers(),
    )
