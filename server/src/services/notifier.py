"""Outbound Telegram delivery for issue matches.

A single Bot instance is shared with the interactive bot (``telegram_bot.py``)."""

from functools import lru_cache
from typing import Any

import structlog
from src.core.config import settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def get_bot() -> Any:
    """Lazily build the shared aiogram Bot. Raises if no token is configured."""
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot

    return Bot(token=settings.telegram_bot_token)


def format_match(
    *,
    repo_full_name: str,
    title: str,
    url: str,
    languages: str | None,
    stars: int,
    body: str,
    relevance: float,
) -> str:
    snippet = " ".join((body or "").split())[:100]
    return (
        f"🔧 {repo_full_name} — {title}\n"
        f"📌 {url}\n"
        f"🏷 Languages: {languages or 'n/a'} | ⭐ Stars: {stars}\n"
        f"💬 {snippet}\n"
        f"Match: {relevance:.2f}"
    )


async def send_text(chat_id: str, text: str) -> None:
    bot = get_bot()
    await bot.send_message(chat_id, text, disable_web_page_preview=True)
