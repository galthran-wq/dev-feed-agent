"""Telegram *inbound*: /start linking + chat_id→user, then hand off to the channel-agnostic
process_incoming. Outbound delivery is a channel (agent/channels/telegram.py)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from src.agent.channels import TelegramChannel, get_bot
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.repositories.users import UserRepository
from src.services import github_oauth
from src.services.messaging import GENERIC_ERROR, process_incoming

logger = structlog.get_logger()

_NOT_LINKED = "This chat isn't linked yet. Link it from the web app first."
_TYPING_INTERVAL = 4.0  # Telegram's "typing…" lasts ~5s; refresh under that.


@asynccontextmanager
async def _typing(chat_id: str) -> AsyncIterator[None]:
    """Show Telegram 'typing…' for the duration — agent turns take seconds. Best-effort:
    re-sent periodically in the background and cancelled once handling finishes."""

    async def _loop() -> None:
        bot = get_bot()
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                return  # typing is cosmetic; never let it disrupt handling
            await asyncio.sleep(_TYPING_INTERVAL)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _send_login_prompt(chat_id: str) -> None:
    """Greet an unlinked chat with a one-tap 'Login with GitHub' button (signed so the chat
    id can't be forged). Falls back to the web-app message if OAuth isn't configured."""
    if not settings.github_oauth_enabled:
        await TelegramChannel(chat_id).send(_NOT_LINKED)
        return
    token = github_oauth.issue_tg_link_token(chat_id)
    url = f"{settings.app_base_url.rstrip('/')}/api/auth/github/login?tg={token}"
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Login with GitHub", url=url)]])
    await get_bot().send_message(
        chat_id,
        "👋 I'm dev-feed-agent — a personalized feed of repos, issues, papers and "
        "discussions for devs & ML engineers, delivered right here.\n\nConnect your GitHub to start:",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def _handle_start(channel: TelegramChannel, chat_id: str, code: str) -> None:
    if not code:
        await _send_login_prompt(chat_id)
        return
    async with AsyncSessionLocal() as session:
        linked = await ConnectionRepository(session).link_telegram(code, chat_id)
    if linked is None:
        await channel.send("That link looks invalid or expired. Grab a fresh one from the web app.")
    else:
        await channel.send(
            "✅ Linked! I'll send your feed here.\n"
            "Chat with me anytime to steer it.\n"
            "Commands: /compact summarize our chat · /reset clear it"
        )


async def handle_update(chat_id: str, text: str) -> None:
    # Detached from the already-acked webhook: never let an exception escape unlogged —
    # the update is marked seen and won't be retried.
    channel = TelegramChannel(chat_id)
    stripped = (text or "").strip()
    try:
        async with _typing(chat_id):
            if stripped.startswith("/start"):
                await _handle_start(channel, chat_id, stripped[len("/start") :].strip())
                return

            async with AsyncSessionLocal() as session:
                conn = await ConnectionRepository(session).get_by_telegram_chat_id(chat_id)
                if conn is None:
                    await _send_login_prompt(chat_id)
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
