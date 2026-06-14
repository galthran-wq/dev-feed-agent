"""Telegram adapter (webhook-only).

Inbound updates arrive at ``POST /api/telegram/webhook`` and are routed here via
``handle_update`` → ``process_incoming`` (the shared, channel-agnostic core). Outbound
text goes through ``notifier`` / ``TelegramChannel``. There is no polling: the bot is
operated purely by webhook, registered with Telegram via ``setup_webhook`` on startup.
"""

import structlog
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.services import notifier
from src.services.channels import TelegramChannel
from src.services.messaging import process_incoming

logger = structlog.get_logger()


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
    """Process one inbound Telegram text message. Resolves the user and delegates to the
    shared ``process_incoming``; ``/start`` (linking) is handled here since it establishes
    the channel itself. Replies go out via the chat's :class:`TelegramChannel`."""
    channel = TelegramChannel(chat_id)
    text = (text or "").strip()

    if text.startswith("/start"):
        await _handle_start(channel, chat_id, text[len("/start") :].strip())
        return

    async with AsyncSessionLocal() as session:
        conn = await ConnectionRepository(session).get_by_telegram_chat_id(chat_id)
        user_id = conn.user_id if conn is not None else None
    if user_id is None:
        await channel.send("This chat isn't linked yet. Link it from the web app first.")
        return

    await process_incoming(channel, user_id, text)


async def setup_webhook() -> None:
    """Register the webhook with Telegram (called on startup when configured)."""
    bot = notifier.get_bot()
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
        bot = notifier.get_bot()
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()
        logger.info("telegram_webhook_deleted")
    except Exception as exc:
        logger.warning("telegram_webhook_delete_failed", error=str(exc))
    finally:
        notifier.get_bot.cache_clear()
