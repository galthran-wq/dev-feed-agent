"""Single, channel-agnostic entry point for an inbound user message.

Every channel adapter — the Telegram inbound handler (``services/channels.py``) and the
HTTP ``POST /api/agent/message`` endpoint — funnels through ``process_incoming``, so "how
to handle a message" lives in one place. Commands (/init, /reset, /compact) are dispatched
here; free text goes to the chat agent. The agent replies via ``send_message`` (its output
channel); control commands send a deterministic acknowledgement on the channel.

Identity and session ownership live with the *caller*: each adapter resolves who the user
is (a chat link, an auth token) within a session it owns, then hands both here. That keeps
this layer free of any transport- or storage-specific lookup, and makes it the single owner
of command dispatch and "something went wrong" error notification.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import Channel
from src.core.config import settings
from src.models.postgres.users import UserModel

logger = structlog.get_logger()

_AGENT_DISABLED = "The agent isn't configured yet."
# Shared so both this layer and the channel adapters (services/channels.py) emit the same
# user-facing apology; one constant, no drift between layers.
GENERIC_ERROR = "Sorry, something went wrong handling that. Try again in a moment."


async def process_incoming(channel: Channel, session: AsyncSession, user: UserModel, text: str) -> None:
    """Handle one inbound message for an already-resolved ``user``, replying via ``channel``.

    The caller owns ``session`` (and the user's lifecycle) so this can run either inside a
    request or detached from one. This function owns command dispatch and error notice.
    """
    text = (text or "").strip()

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
            logger.error("compact_failed", user_id=str(user.id), error=str(exc))
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
        logger.error("chat_failed", user_id=str(user.id), error=str(exc))
        await channel.send(GENERIC_ERROR)
