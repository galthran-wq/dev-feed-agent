"""Telegram webhook — the bot's single inbound channel (no polling).

Telegram POSTs each update here. We verify the shared secret, dedup the ``update_id``
(delivery is at-least-once), then **fast-ack** with 200 and process the message detached
(``asyncio.create_task``) — agent runs take seconds and Telegram would otherwise retry
and double-fire. ``handle_update`` resolves the user (and handles ``/start`` linking) and
delegates to the shared, channel-agnostic ``process_incoming``; replies go out via the
chat's :class:`TelegramChannel`. Webhook registration lives in ``services/channels.py``.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import AsyncSessionLocal, get_postgres_session
from src.core.exceptions import AppError
from src.repositories.connections import ConnectionRepository
from src.repositories.processed_updates import ProcessedUpdateRepository
from src.services.channels import TelegramChannel
from src.services.messaging import process_incoming

logger = structlog.get_logger()

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


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
    """Process one inbound text message. Resolves the user and delegates to the shared
    ``process_incoming``; ``/start`` (linking) is handled here since it establishes the
    channel itself.

    Runs detached from the (already-acked) request, so it must never let an exception
    escape unlogged — the update is already marked seen and won't be retried.
    """
    channel = TelegramChannel(chat_id)
    text = (text or "").strip()
    try:
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
    except Exception as exc:
        logger.error("telegram_update_failed", chat_id=chat_id, error=str(exc))
        try:
            await channel.send("Sorry, something went wrong handling that. Try again in a moment.")
        except Exception:
            logger.error("telegram_error_notice_failed", chat_id=chat_id)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_postgres_session),
) -> Response:
    # The shared secret is the gate (it's required for the app to start, so it's always
    # set in a running instance). A missing/wrong header never reaches processing.
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise AppError(status_code=403, detail="Invalid webhook secret")

    data = await request.json()
    update_id = data.get("update_id")
    message = data.get("message")
    if not isinstance(update_id, int) or not isinstance(message, dict):
        # Non-message / malformed update (we only subscribe to "message") — ack & drop.
        return Response(status_code=200)

    # At-least-once delivery → dedup before doing any work with side effects.
    if await ProcessedUpdateRepository(session).seen_or_mark(update_id):
        return Response(status_code=200)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        return Response(status_code=200)

    # Fast-ack: process detached so we return 200 well within Telegram's timeout.
    asyncio.create_task(handle_update(str(chat_id), text))  # noqa: RUF006
    return Response(status_code=200)
