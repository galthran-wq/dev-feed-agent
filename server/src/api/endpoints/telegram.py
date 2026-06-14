"""Telegram webhook — the bot's single inbound channel (no polling).

This module is pure transport: Telegram POSTs each update here, we verify the shared
secret, dedup the ``update_id`` (delivery is at-least-once), then **fast-ack** with 200 and
hand the message to ``services.channels.handle_update`` detached (``asyncio.create_task``)
— agent runs take seconds and Telegram would otherwise retry and double-fire. All the
Telegram message orchestration (linking, user resolution, dispatch) lives in
``services/channels.py``; webhook registration lives there too.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.repositories.processed_updates import ProcessedUpdateRepository
from src.services.channels import handle_update

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
    if not isinstance(update_id, int) or not isinstance(message, dict):
        # Non-message / malformed update (we only subscribe to "message") — ack & drop.
        return Response(status_code=200)

    # At-least-once delivery → dedup before doing any work with side effects.
    if await ProcessedUpdateRepository(session).seen_or_mark(update_id):
        return Response(status_code=200)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None or not text or not text.strip():
        return Response(status_code=200)

    # Fast-ack: process detached so we return 200 well within Telegram's timeout.
    asyncio.create_task(handle_update(str(chat_id), text))  # noqa: RUF006
    return Response(status_code=200)
