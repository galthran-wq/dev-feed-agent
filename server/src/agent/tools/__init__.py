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

# Typed as list[Any] because pydantic-ai accepts heterogeneous tool callables; mypy
# otherwise joins the distinct async-function types down to `function`.
# Both agents get send_message: the chat agent answers/delivers the feed with it, and the
# profile agent uses it to tell the user the profile is ready.
PROFILE_TOOLS: list[Any] = [*GITHUB_TOOLS, *MEMORY_TOOLS, *MESSAGING_TOOLS]
CHAT_TOOLS: list[Any] = [*GITHUB_TOOLS, *FEED_TOOLS, *MEMORY_TOOLS, *MESSAGING_TOOLS]

__all__ = ["CHAT_TOOLS", "FEED_TOOLS", "GITHUB_TOOLS", "MEMORY_TOOLS", "MESSAGING_TOOLS", "PROFILE_TOOLS"]
