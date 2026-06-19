"""pydantic-ai tool functions, grouped by concern.

``github_tools`` — read a user's GitHub footprint (repos, stars, dependencies) for
profiling. ``feed_tools`` — search GitHub for fresh feed candidates. ``memory_tools``
— read/patch the agent's durable memory (profile + already-shown items).
"""

from typing import Any

from src.agent.tools.feed_tools import FEED_TOOLS
from src.agent.tools.github_tools import GITHUB_TOOLS
from src.agent.tools.memory_tools import MAIN_MEMORY_TOOLS, MEMORY_TOOLS
from src.agent.tools.messaging_tools import MESSAGING_TOOLS
from src.agent.tools.schedule_tools import SCHEDULE_TOOLS
from src.agent.tools.subagent_tools import SUBAGENT_TOOLS

# Typed as list[Any] because pydantic-ai accepts heterogeneous tool callables; mypy
# otherwise joins the distinct async-function types down to `function`.
# BASE_TOOLS is the SUB-AGENT toolset; MAIN_TOOLS adds what only the main agent may do.
# Sub-agents get neither send_message (only the main agent talks to the user — they report back)
# nor spawn_subagent (anti-recursion) nor add_memory (only the main agent authors user memories;
# routine remembering is passive). All exclusions are structural, not prompt-enforced.
BASE_TOOLS: list[Any] = [*GITHUB_TOOLS, *FEED_TOOLS, *MEMORY_TOOLS]
MAIN_TOOLS: list[Any] = [*BASE_TOOLS, *MAIN_MEMORY_TOOLS, *MESSAGING_TOOLS, *SUBAGENT_TOOLS, *SCHEDULE_TOOLS]

__all__ = ["BASE_TOOLS", "FEED_TOOLS", "GITHUB_TOOLS", "MAIN_TOOLS", "MEMORY_TOOLS", "MESSAGING_TOOLS"]
