"""Agent factories.

A fresh ``Agent`` per run avoids shared mutable state across concurrent requests.
``make_chat_agent`` is async because it probes its MCP sources first (see ``mcp.py``).
"""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from src.agent.deps import AgentDeps
from src.agent.mcp import reachable_mcp_servers
from src.agent.tools import BASE_TOOLS, MAIN_TOOLS
from src.core.config import settings

_PROMPTS = Path(__file__).parent / "prompts"


@lru_cache
def _prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _model(name: str) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=settings.openrouter_base_url, api_key=settings.openrouter_api_key)
    return OpenAIChatModel(name, provider=provider)


def _today_note() -> str:
    """The model has no clock — without this it invents the date (and advances it off the
    previous digest in the shared history). Inject the real date so any date it writes is right."""
    today = datetime.now(UTC)
    return (
        f"The current date is {today:%Y-%m-%d} ({today:%A, %d %B %Y}). Use this for any date you "
        "mention (e.g. a feed heading). Never guess, invent, or advance the date, and ignore "
        "dates that appear in earlier messages — only this one is authoritative."
    )


async def make_subagent(prompt_file: str, model_name: str) -> Agent[AgentDeps, str]:
    """A sub-agent gets BASE_TOOLS (everything the main agent has *except* spawn_subagent —
    the structural anti-recursion guarantee) plus the same reachable MCP sources as chat."""
    return Agent(
        _model(model_name),
        deps_type=AgentDeps,
        system_prompt=_prompt(prompt_file),
        tools=BASE_TOOLS,
        toolsets=await reachable_mcp_servers(),
    )


def make_summarizer_agent() -> Agent[None, str]:
    return Agent(
        _model(settings.agent_model),
        system_prompt=(
            "You compact a conversation for your future self. Given the prior messages, write a "
            "tight note capturing durable facts about the user, their stated preferences, current "
            "focus, and what's already been shown. Be concise; omit small talk. Do not call tools."
        ),
    )


async def make_chat_agent() -> Agent[AgentDeps, str]:
    """Wires in only reachable MCP sources so a dead one is skipped, not fatal to the run."""
    agent = Agent(
        _model(settings.agent_model),
        deps_type=AgentDeps,
        # Date note FIRST so it's at the very top of the system prompt — most salient, least
        # likely to be drowned out by the long instructions below.
        system_prompt=(_today_note(), _prompt("chat.md")),
        tools=MAIN_TOOLS,
        toolsets=await reachable_mcp_servers(),
    )

    @agent.system_prompt
    def _channel_format(ctx: RunContext[AgentDeps]) -> str:
        # The channel decides the markup; tell the agent how to format for wherever it delivers.
        channel = ctx.deps.channel
        return f"## Formatting for this channel\n\n{channel.format_instructions}" if channel else ""

    return agent
