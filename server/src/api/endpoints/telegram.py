"""Telegram webhook — pure transport: verify secret, dedup update_id, fast-ack, run
handle_update detached. Fast-ack because agent runs take seconds and Telegram retries
(and double-fires) on a slow ack. Inbound logic: services/telegram.py."""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.repositories.processed_updates import ProcessedUpdateRepository
from src.services.telegram import handle_update

logger = structlog.get_logger()

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_postgres_session),
) -> Response:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise AppError(status_code=403, detail="Invalid webhook secret")

    data = await request.json()
    update_id = data.get("update_id")
    message = data.get("message")
    if not isinstance(update_id, int) or not isinstance(message, dict):
        return Response(status_code=200)  # non-message/malformed — ack & drop

    # At-least-once delivery → dedup before any side-effecting work.
    if await ProcessedUpdateRepository(session).seen_or_mark(update_id):
        return Response(status_code=200)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None or not text or not text.strip():
        return Response(status_code=200)

    asyncio.create_task(handle_update(str(chat_id), text))  # noqa: RUF006
    return Response(status_code=200)
