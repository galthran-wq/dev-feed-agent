"""Telegram webhook: the single inbound channel for the bot.

Telegram POSTs each update here. We verify the shared secret, dedup the ``update_id``
(delivery is at-least-once), then **fast-ack** with 200 and process the message detached
(``asyncio.create_task``) — agent runs take seconds and Telegram would otherwise retry
and double-fire. Replies are sent by the agent via ``send_message`` / ``TelegramChannel``.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.repositories.processed_updates import ProcessedUpdateRepository
from src.services import telegram_bot

logger = structlog.get_logger()

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


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
    if update_id is None or not isinstance(message, dict):
        # Non-message update (we only subscribe to "message", but be defensive) — ack & drop.
        return Response(status_code=200)

    # At-least-once delivery → dedup before doing any work with side effects.
    if await ProcessedUpdateRepository(session).seen_or_mark(int(update_id)):
        return Response(status_code=200)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if chat_id is None or not text:
        return Response(status_code=200)

    # Fast-ack: process detached so we return 200 well within Telegram's timeout.
    asyncio.create_task(telegram_bot.handle_update(str(chat_id), text))  # noqa: RUF006
    return Response(status_code=200)
