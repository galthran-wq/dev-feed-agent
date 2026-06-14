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

logger = structlog.get_logger()

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
