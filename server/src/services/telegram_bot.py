"""Interactive aiogram bot: links a Telegram chat to a user, rebuilds the profile on
/init, and routes free text to the memory-aware chat agent. Runs as a background task
off the FastAPI lifespan."""

import asyncio
import contextlib
from typing import Any

import structlog
from src.agent import runtime
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.repositories.users import UserRepository
from src.services import notifier

logger = structlog.get_logger()

_task: asyncio.Task[None] | None = None


async def _user_for_chat(session: Any, chat_id: str) -> Any:
    conn = await ConnectionRepository(session).get_by_telegram_chat_id(chat_id)
    if conn is None:
        return None
    return await UserRepository(session).get_user(conn.user_id)


def _build_dispatcher() -> Any:
    from aiogram import Dispatcher, F
    from aiogram.filters import Command, CommandObject, CommandStart
    from aiogram.types import Message

    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: Message, command: CommandObject) -> None:
        chat_id = str(message.chat.id)
        code = (command.args or "").strip()
        if not code:
            await message.answer(
                "👋 I'm dev-feed-agent. I deliver a personalized feed of repos, issues, "
                "papers and discussions.\nOpen the web app and tap “Go to Telegram” to link this chat."
            )
            return
        async with AsyncSessionLocal() as session:
            linked = await ConnectionRepository(session).link_telegram(code, chat_id)
        if linked is None:
            await message.answer("That link looks invalid or expired. Grab a fresh one from the web app.")
        else:
            await message.answer(
                "✅ Linked! I'll send your feed here.\n"
                "Chat with me anytime to steer it, or send /init to (re)build your profile."
            )

    @dp.message(Command("init"))
    async def on_init(message: Message) -> None:
        if not settings.agent_enabled:
            await message.answer("The agent isn't configured yet.")
            return
        async with AsyncSessionLocal() as session:
            user = await _user_for_chat(session, str(message.chat.id))
            if user is None:
                await message.answer("This chat isn't linked yet. Link it from the web app first.")
                return
            user_id = user.id
        await message.answer("🔧 Rebuilding your interest profile from your GitHub activity…")
        asyncio.create_task(runtime.build_profile_safe(user_id))  # noqa: RUF006

    @dp.message(F.text)
    async def on_text(message: Message) -> None:
        if not settings.agent_enabled:
            await message.answer("The agent isn't configured yet.")
            return
        try:
            async with AsyncSessionLocal() as session:
                user = await _user_for_chat(session, str(message.chat.id))
                if user is None:
                    await message.answer("This chat isn't linked yet. Link it from the web app first.")
                    return
                reply = await runtime.chat(session, user, message.text or "")
        except Exception as exc:
            logger.error("telegram_chat_failed", error=str(exc))
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
    # The polling task closed the shared Bot's session in its finally block; drop the
    # cached instance so a subsequent start_bot() (and notifier delivery) gets a fresh one.
    notifier.get_bot.cache_clear()
