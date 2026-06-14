"""Channels — *where* an agent run sends user-facing text.

``base`` holds the :class:`Channel` port plus the in-memory :class:`CollectingChannel`
(HTTP responses + tests); ``telegram`` holds the :class:`TelegramChannel` adapter and the
shared bot / webhook lifecycle. Inbound Telegram handling is **not** a channel — it lives
in ``services/telegram.py``.
"""

from src.agent.channels.base import Channel, CollectingChannel
from src.agent.channels.telegram import TelegramChannel, get_bot, remove_webhook, setup_webhook

__all__ = [
    "Channel",
    "CollectingChannel",
    "TelegramChannel",
    "get_bot",
    "remove_webhook",
    "setup_webhook",
]
