"""Interactive aiogram bot: links a Telegram chat to a user and lets them refine
their interest profile by chatting. Runs as a background task off the FastAPI lifespan."""

import asyncio
import contextlib
from typing import Any

import structlog
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.github_profiles import GithubProfileRepository
from src.services import interest_service, notifier

logger = structlog.get_logger()

_task: asyncio.Task[None] | None = None


async def _handle_refine(chat_id: str, text: str) -> str:
    """Process a free-text message from a linked chat and return the agent's reply."""
    async with AsyncSessionLocal() as session:
        profile = await GithubProfileRepository(session).get_by_telegram_chat_id(chat_id)
        if profile is None:
            return "This chat isn't linked yet. Open the web app and tap “Go to Telegram” to connect."
        result = await interest_service.refine_for_user(session, profile.user_id, text)
        return result.reply


def _build_dispatcher() -> Any:
    from aiogram import Dispatcher, F
    from aiogram.filters import CommandObject, CommandStart
    from aiogram.types import Message

    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: Message, command: CommandObject) -> None:
        chat_id = str(message.chat.id)
        code = (command.args or "").strip()
        if not code:
            await message.answer(
                "👋 I deliver GitHub good-first-issues matched to your interests.\n"
                "Open the web app and tap “Go to Telegram” to link this chat."
            )
            return
        async with AsyncSessionLocal() as session:
            linked = await GithubProfileRepository(session).link_telegram(code, chat_id)
        if linked is None:
            await message.answer("That link looks invalid or expired. Grab a fresh one from the web app.")
        else:
            await message.answer(
                "✅ Linked! I'll send you matching good-first-issues here.\n"
                "You can also just chat with me to refine what you're interested in."
            )

    @dp.message(F.text)
    async def on_text(message: Message) -> None:
        if not settings.agent_enabled:
            await message.answer("The interest agent isn't configured yet.")
            return
        try:
            reply = await _handle_refine(str(message.chat.id), message.text or "")
        except Exception as exc:
            logger.error("telegram_refine_failed", error=str(exc))
            reply = "Sorry, something went wrong handling that. Try again in a moment."
        await message.answer(reply)

    return dp


async def _run() -> None:
    bot = notifier.get_bot()
    dp = _build_dispatcher()
    logger.info("telegram_bot_polling_started")
    try:
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        logger.info("telegram_bot_polling_cancelled")
        raise
    finally:
        await bot.session.close()


def start_bot() -> None:
    global _task
    if _task is not None or not settings.telegram_enabled:
        return
    _task = asyncio.create_task(_run())


async def stop_bot() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None
