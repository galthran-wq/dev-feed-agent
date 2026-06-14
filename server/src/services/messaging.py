"""Single, channel-agnostic entry point for an inbound user message.

Every channel adapter — the Telegram webhook (and the optional polling fallback) and the
HTTP ``POST /api/agent/message`` endpoint — funnels through ``process_incoming``, so "how
to handle a message" lives in one place. Commands (/init, /reset, /compact) are dispatched
here; free text goes to the chat agent. The agent replies via ``send_message`` (its
output channel); control commands send a deterministic acknowledgement on the channel.

This is the seam a real job queue would slot behind later — it already owns its own DB
session, so it is safe to run detached from any request lifecycle (``asyncio.create_task``).
"""

from uuid import UUID

import structlog
from src.agent import runtime
from src.agent.channels import Channel
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.users import UserRepository

logger = structlog.get_logger()

_AGENT_DISABLED = "The agent isn't configured yet."
_NOT_LINKED = "This chat isn't linked yet. Link it from the web app first."


async def process_incoming(channel: Channel, user_id: UUID, text: str) -> None:
    """Handle one inbound message for ``user_id``, replying via ``channel``.

    Opens its own session so it can run detached from the request that received the
    message (the webhook fast-acks and schedules this).
    """
    text = (text or "").strip()
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_user(user_id)
        if user is None:
            await channel.send(_NOT_LINKED)
            return

        if text == "/reset":
            await runtime.reset(session, user)
            await channel.send("🧹 Cleared our conversation history. Your interest profile is kept.")
            return

        if text == "/init":
            if not settings.agent_enabled:
                await channel.send(_AGENT_DISABLED)
                return
            await channel.send("🔧 Rebuilding your interest profile from your GitHub activity…")
            # build_profile_safe manages its own session and tells the user when done.
            await runtime.build_profile_safe(user.id, channel)
            return

        if text == "/compact":
            if not settings.agent_enabled:
                await channel.send(_AGENT_DISABLED)
                return
            try:
                summary = await runtime.compact(session, user)
            except Exception as exc:
                logger.error("compact_failed", user_id=str(user_id), error=str(exc))
                await channel.send("Sorry, couldn't compact just now. Try again in a moment.")
                return
            await channel.send(f"🗜 Compacted. Carrying forward:\n\n{summary}")
            return

        # Free text → the memory-aware chat agent (it replies via send_message).
        if not settings.agent_enabled:
            await channel.send(_AGENT_DISABLED)
            return
        try:
            await runtime.chat(session, user, text, channel)
        except Exception as exc:
            logger.error("chat_failed", user_id=str(user_id), error=str(exc))
            await channel.send("Sorry, something went wrong handling that. Try again in a moment.")
