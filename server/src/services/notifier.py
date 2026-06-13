"""Outbound Telegram delivery.

The agent writes the feed as free-form text, so we send it verbatim (plain text —
no Markdown parsing to choke on arbitrary content), chunked under Telegram's limit.
A single Bot instance is shared with the interactive bot (``telegram_bot.py``).
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
    """Split text into <=limit pieces, preferring line boundaries."""
    out: list[str] = []
    buf = ""
    for line in text.split("\n"):
        candidate = f"{buf}\n{line}" if buf else line
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf:
            out.append(buf)
        # A single line longer than the limit is hard-split.
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        buf = line
    if buf:
        out.append(buf)
    return out or [""]


async def send_text(chat_id: str, text: str) -> None:
    bot = get_bot()
    for chunk in _chunks(text):
        await bot.send_message(chat_id, chunk, disable_web_page_preview=True)
