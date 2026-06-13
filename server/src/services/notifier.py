"""Outbound Telegram delivery for feed items.

A single Bot instance is shared with the interactive bot (``telegram_bot.py``).
"""

from functools import lru_cache
from typing import Any

import structlog
from src.core.config import settings
from src.models.postgres.feed_items import FeedItemModel

logger = structlog.get_logger()

_SOURCE_ICON = {
    "github": "🐙",
    "hf": "🤗",
    "huggingface": "🤗",
    "hackernews": "🟠",
    "arxiv": "📄",
    "reddit": "👽",
}


@lru_cache(maxsize=1)
def get_bot() -> Any:
    """Lazily build the shared aiogram Bot. Raises if no token is configured."""
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram bot token is not configured")
    from aiogram import Bot

    return Bot(token=settings.telegram_bot_token)


def format_feed_item(item: FeedItemModel) -> str:
    icon = _SOURCE_ICON.get(item.source, "🔹")
    bucket = "🧭 explore" if item.bucket == "explore" else "🎯 for you"
    lines = [
        f"{icon} *{_escape(item.title)}*",
        f"{item.url}",
    ]
    if item.summary:
        lines.append(f"_{_escape(item.summary[:200])}_")
    if item.reason:
        lines.append(f"💡 {_escape(item.reason)}")
    lines.append(f"{bucket} · match {item.score:.2f}")
    return "\n".join(lines)


def _escape(text: str) -> str:
    # Minimal escaping for Telegram Markdown (v1): defang the markers we don't intend.
    return text.replace("*", "∗").replace("_", " ").replace("`", "'").replace("[", "(").replace("]", ")")


async def send_text(chat_id: str, text: str) -> None:
    bot = get_bot()
    await bot.send_message(chat_id, text, parse_mode="Markdown", disable_web_page_preview=True)
