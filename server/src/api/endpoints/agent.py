"""Auth-scoped agent endpoints. The web app only needs status + the Telegram link;
all interaction happens in Telegram. ``rebuild`` and ``poll-now`` are thin triggers."""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import Channel, CollectingChannel, TelegramChannel
from src.core.auth import get_current_user
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.models.postgres.connections import ConnectionModel
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.schemas.agent import (
    MessageRequest,
    MessageResponse,
    PollNowResponse,
    RebuildResponse,
    StatusResponse,
    TelegramLinkResponse,
)
from src.services import feed
from src.services.messaging import process_incoming

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _telegram_channel(conn: ConnectionModel) -> Channel | None:
    """The user's Telegram channel if this chat is linked, else None.

    Telegram is required for the app to boot (see ``main.lifespan``), so ``telegram_enabled``
    is invariably true at runtime — the only question is whether *this* chat is linked. This
    matches how ``scheduler.poll_all_users`` builds the channel.
    """
    if conn.telegram_chat_id:
        return TelegramChannel(conn.telegram_chat_id)
    return None


@router.get("/status", response_model=StatusResponse)
async def get_status(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> StatusResponse:
    conn = await ConnectionRepository(session).get_or_create(current_user.id)
    built = await ProfileRepository(session).is_built(current_user.id)
    return StatusResponse(
        github_connected=bool(current_user.github_id),
        github_username=current_user.github_username,
        avatar_url=current_user.avatar_url,
        telegram_linked=bool(conn.telegram_chat_id),
        profile_built=built,
        agent_enabled=settings.agent_enabled,
    )


@router.get("/telegram-link", response_model=TelegramLinkResponse)
async def get_telegram_link(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> TelegramLinkResponse:
    conn = await ConnectionRepository(session).get_or_create(current_user.id)
    bot_configured = settings.telegram_enabled and bool(settings.telegram_bot_username)
    url = None
    if bot_configured:
        url = f"https://t.me/{settings.telegram_bot_username}?start={conn.telegram_link_code}"
    return TelegramLinkResponse(linked=bool(conn.telegram_chat_id), url=url, bot_configured=bot_configured)


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild_profile(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> RebuildResponse:
    if not current_user.github_username:
        raise AppError(status_code=400, detail="Connect your GitHub account first")
    if not settings.agent_enabled:
        raise AppError(status_code=503, detail="LLM agent is not configured (set OPENROUTER_API_KEY)")
    conn = await ConnectionRepository(session).get_or_create(current_user.id)
    # If a Telegram chat is linked, the profile agent will message it when done.
    channel = _telegram_channel(conn)
    asyncio.create_task(runtime.build_profile_safe(current_user.id, channel))  # noqa: RUF006
    return RebuildResponse(status="building", message="Rebuilding your interest profile from GitHub activity.")


@router.post("/poll-now", response_model=PollNowResponse)
async def poll_now(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> PollNowResponse:
    """Dev/testing trigger: run one feed pass for the current user now (delivers to Telegram if linked)."""
    conn = await ConnectionRepository(session).get_or_create(current_user.id)
    result = await feed.run_for_user(session, conn, channel=_telegram_channel(conn))
    return PollNowResponse(
        delivered=result.delivered,
        curated=result.curated,
        message=result.note or f"Curated {result.curated} items",
    )


@router.post("/message", response_model=MessageResponse)
async def post_message(
    body: MessageRequest,
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> MessageResponse:
    """Send a message to the agent over HTTP and get its reply.

    Same core as Telegram: routes through ``process_incoming``. The authenticated user and
    request session are passed straight through (no re-resolution); the agent talks via
    ``send_message``, and here those messages are buffered in a CollectingChannel and returned.
    """
    channel = CollectingChannel()
    await process_incoming(channel, session, current_user, body.message)
    return MessageResponse(messages=channel.messages)
