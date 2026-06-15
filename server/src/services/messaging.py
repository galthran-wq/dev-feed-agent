"""Channel-agnostic entry for an inbound message: dispatch /reset·/compact, else chat.
The caller owns the session and the resolved user, so this runs in-request or detached.

There is no /init: a new user's first free-text message goes to the chat agent, which detects
an empty profile and spawns the profile_build sub-agent itself (no canned text)."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import Channel
from src.core.config import settings
from src.models.postgres.users import UserModel

logger = structlog.get_logger()

_AGENT_DISABLED = "The agent isn't configured yet."
# One shared constant so this layer and the Telegram adapter can't drift on the wording.
GENERIC_ERROR = "Sorry, something went wrong handling that. Try again in a moment."


async def process_incoming(channel: Channel, session: AsyncSession, user: UserModel, text: str) -> None:
    text = (text or "").strip()

    if text == "/reset":
        await runtime.reset(session, user)
        await channel.send("🧹 Cleared our conversation history. Your interest profile is kept.")
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

    # Free text → chat agent (it replies via send_message).
    if not settings.agent_enabled:
        await channel.send(_AGENT_DISABLED)
        return
    try:
        await runtime.chat(session, user, text, channel)
    except Exception as exc:
        logger.error("chat_failed", user_id=str(user.id), error=str(exc))
        await channel.send(GENERIC_ERROR)
