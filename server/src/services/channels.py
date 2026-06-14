"""Telegram delivery: the shared Bot client, message chunking, and the ``TelegramChannel``
adapter that implements the agent's :class:`src.agent.channels.Channel` over it.

This is the services-side counterpart to the abstract ``Channel`` in the agent layer.
``get_bot`` is the one aiogram ``Bot`` instance, reused both for sending and for webhook
registration (``setup_webhook``/``remove_webhook`` below). A future web/SSE channel would
live here too. Inbound updates are handled by the webhook endpoint (``api/endpoints/telegram.py``).
"""

from functools import lru_cache
from typing import Any

import structlog
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.repositories.users import UserRepository
from src.services.messaging import GENERIC_ERROR, process_incoming

logger = structlog.get_logger()

_NOT_LINKED = "This chat isn't linked yet. Link it from the web app first."

_TELEGRAM_LIMIT = 4096


@lru_cache(maxsize=1)
def get_bot() -> Any:
    """Lazily build the shared aiogram Bot. Raises if no token is configured."""
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot

    return Bot(token=settings.telegram_bot_token)


def _chunks(text: str, limit: int = _TELEGRAM_LIMIT) -> list[str]:
    """Split text into <=limit pieces, preferring line boundaries.

    Uses a None sentinel for "empty buffer" so blank lines are preserved (an empty
    string is falsy but is real content — dropping it would merge paragraphs).
    """
    out: list[str] = []
    buf: str | None = None
    for line in text.split("\n"):
        candidate = line if buf is None else f"{buf}\n{line}"
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf is not None:
            out.append(buf)
        # A single line longer than the limit is hard-split.
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        buf = line
    if buf is not None:
        out.append(buf)
    return out or [""]


class TelegramChannel:
    """A :class:`src.agent.channels.Channel` that delivers to one Telegram chat.

    Structural-typed (no explicit base) so the agent layer never imports services. Sends
    free-form text verbatim (plain text — no Markdown parsing to choke on arbitrary
    content), chunked under Telegram's per-message limit.
    """

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        bot = get_bot()
        for chunk in _chunks(text):
            await bot.send_message(self.chat_id, chunk, disable_web_page_preview=True)


async def _handle_start(channel: TelegramChannel, chat_id: str, code: str) -> None:
    """`/start [<code>]` — link this chat to a user (or greet if no code)."""
    if not code:
        await channel.send(
            "👋 I'm dev-feed-agent. I deliver a personalized feed of repos, issues, "
            "papers and discussions.\nOpen the web app and tap “Go to Telegram” to link this chat."
        )
        return
    async with AsyncSessionLocal() as session:
        linked = await ConnectionRepository(session).link_telegram(code, chat_id)
    if linked is None:
        await channel.send("That link looks invalid or expired. Grab a fresh one from the web app.")
    else:
        await channel.send(
            "✅ Linked! I'll send your feed here.\n"
            "Chat with me anytime to steer it.\n"
            "Commands: /init rebuild profile · /compact summarize our chat · /reset clear it"
        )


async def handle_update(chat_id: str, text: str) -> None:
    """Process one inbound Telegram text message.

    This is the Telegram inbound adapter: it owns everything transport-specific — building
    the channel, ``/start`` linking, and the chat_id→user resolution — then hands the
    resolved user to the channel-agnostic ``process_incoming``. It opens one session for the
    whole turn, so identity resolution and the agent run share it.

    Runs detached from the (already-acked) webhook, so it must never let an exception escape
    unlogged — the update is already marked seen and won't be retried.
    """
    channel = TelegramChannel(chat_id)
    stripped = (text or "").strip()
    try:
        if stripped.startswith("/start"):
            await _handle_start(channel, chat_id, stripped[len("/start") :].strip())
            return

        async with AsyncSessionLocal() as session:
            conn = await ConnectionRepository(session).get_by_telegram_chat_id(chat_id)
            if conn is None:
                await channel.send(_NOT_LINKED)
                return
            user = await UserRepository(session).get_user(conn.user_id)
            if user is None:
                # Connection exists but the user is gone — shouldn't happen; treat as an error.
                logger.error("telegram_chat_user_missing", chat_id=chat_id, user_id=str(conn.user_id))
                await channel.send(GENERIC_ERROR)
                return
            await process_incoming(channel, session, user, text)
    except Exception as exc:
        logger.error("telegram_update_failed", chat_id=chat_id, error=str(exc))
        try:
            await channel.send(GENERIC_ERROR)
        except Exception:
            logger.error("telegram_error_notice_failed", chat_id=chat_id)


async def setup_webhook() -> None:
    """Register the webhook with Telegram (called on startup). Uses the shared Bot."""
    bot = get_bot()
    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    logger.info("telegram_webhook_set", url=settings.telegram_webhook_url)


async def remove_webhook() -> None:
    """Deregister the webhook and drop the cached Bot (called on shutdown)."""
    try:
        bot = get_bot()
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()
        logger.info("telegram_webhook_deleted")
    except Exception as exc:
        logger.warning("telegram_webhook_delete_failed", error=str(exc))
    finally:
        get_bot.cache_clear()
