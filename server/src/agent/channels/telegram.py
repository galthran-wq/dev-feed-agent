"""Telegram output channel: shared bot, message chunking, the TelegramChannel adapter.
Inbound updates are a separate concern — see services/telegram.py."""

from functools import lru_cache
from typing import Any

import structlog
from src.core.config import settings

logger = structlog.get_logger()

_TELEGRAM_LIMIT = 4096


@lru_cache(maxsize=1)
def get_bot() -> Any:
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot  # lazy: importing this module must not pull in the transport

    return Bot(token=settings.telegram_bot_token)


def _chunks(text: str, limit: int = _TELEGRAM_LIMIT) -> list[str]:
    out: list[str] = []
    # None (not "") for "empty buffer" so blank lines survive — dropping them merges paragraphs.
    buf: str | None = None
    for line in text.split("\n"):
        candidate = line if buf is None else f"{buf}\n{line}"
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf is not None:
            out.append(buf)
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        buf = line
    if buf is not None:
        out.append(buf)
    return out or [""]


class TelegramChannel:
    # Plain text, never Markdown — arbitrary feed content would choke Telegram's parser.
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        bot = get_bot()
        for chunk in _chunks(text):
            await bot.send_message(self.chat_id, chunk, disable_web_page_preview=True)


async def setup_webhook() -> None:
    bot = get_bot()
    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.telegram_webhook_secret,
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    logger.info("telegram_webhook_set", url=settings.telegram_webhook_url)


async def remove_webhook() -> None:
    try:
        bot = get_bot()
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()
        logger.info("telegram_webhook_deleted")
    except Exception as exc:
        logger.warning("telegram_webhook_delete_failed", error=str(exc))
    finally:
        get_bot.cache_clear()
