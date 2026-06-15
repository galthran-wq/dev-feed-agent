"""pydantic-ai tool functions, grouped by concern.

``github_tools`` — read a user's GitHub footprint (repos, stars, dependencies) for
profiling. ``feed_tools`` — search GitHub for fresh feed candidates. ``memory_tools``
— read/patch the agent's durable memory (profile + already-shown items).
"""

from typing import Any

from src.agent.tools.feed_tools import FEED_TOOLS
from src.agent.tools.github_tools import GITHUB_TOOLS
from src.agent.tools.memory_tools import MEMORY_TOOLS
from src.agent.tools.messaging_tools import MESSAGING_TOOLS
from src.agent.tools.subagent_tools import SUBAGENT_TOOLS

# Typed as list[Any] because pydantic-ai accepts heterogeneous tool callables; mypy
# otherwise joins the distinct async-function types down to `function`.
# BASE_TOOLS: every agent, main or sub. MAIN_TOOLS = BASE + the spawn tool. Sub-agents get
# BASE_TOOLS only — withholding spawn_subagent is the structural anti-recursion guarantee.
BASE_TOOLS: list[Any] = [*GITHUB_TOOLS, *FEED_TOOLS, *MEMORY_TOOLS, *MESSAGING_TOOLS]
MAIN_TOOLS: list[Any] = [*BASE_TOOLS, *SUBAGENT_TOOLS]

__all__ = ["BASE_TOOLS", "FEED_TOOLS", "GITHUB_TOOLS", "MAIN_TOOLS", "MEMORY_TOOLS", "MESSAGING_TOOLS"]
