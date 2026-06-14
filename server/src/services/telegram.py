"""Telegram *inbound*: /start linking + chat_id→user, then hand off to the channel-agnostic
process_incoming. Outbound delivery is a channel (agent/channels/telegram.py)."""

import structlog
from src.agent.channels import TelegramChannel
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.repositories.users import UserRepository
from src.services.messaging import GENERIC_ERROR, process_incoming

logger = structlog.get_logger()

_NOT_LINKED = "This chat isn't linked yet. Link it from the web app first."


async def _handle_start(channel: TelegramChannel, chat_id: str, code: str) -> None:
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
    # Detached from the already-acked webhook: never let an exception escape unlogged —
    # the update is marked seen and won't be retried.
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
            if user is None:  # connection exists but user gone — shouldn't happen
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
