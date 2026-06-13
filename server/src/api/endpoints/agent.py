"""Auth-scoped agent endpoints. The web app only needs status + the Telegram link;
all interaction happens in Telegram. ``rebuild`` and ``poll-now`` are thin triggers."""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.core.auth import get_current_user
from src.core.config import settings
from src.core.cooldown import cooldown_remaining
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.schemas.agent import (
    PollNowResponse,
    RebuildResponse,
    StatusResponse,
    TelegramLinkResponse,
)
from src.services import feed

router = APIRouter(prefix="/api/agent", tags=["agent"])


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
    repo = ConnectionRepository(session)
    conn = await repo.get_or_create(current_user.id)
    wait = cooldown_remaining(conn.last_profile_build_at, settings.rebuild_cooldown_seconds)
    if wait:
        raise AppError(status_code=429, detail=f"Profile rebuild is on cooldown; retry in {wait}s")
    # Stamp before kicking off the fire-and-forget build so concurrent calls are gated.
    await repo.mark_profile_build_started(conn)
    asyncio.create_task(runtime.build_profile_safe(current_user.id))  # noqa: RUF006
    return RebuildResponse(status="building", message="Rebuilding your interest profile from GitHub activity.")


@router.post("/poll-now", response_model=PollNowResponse)
async def poll_now(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> PollNowResponse:
    """Dev/testing trigger: run one feed pass for the current user now."""
    conn = await ConnectionRepository(session).get_or_create(current_user.id)
    wait = cooldown_remaining(conn.last_feed_at, settings.poll_now_cooldown_seconds)
    if wait:
        raise AppError(status_code=429, detail=f"Feed poll is on cooldown; retry in {wait}s")
    result = await feed.run_for_user(session, conn)
    return PollNowResponse(
        delivered=result.delivered,
        curated=result.curated,
        message=result.note or f"Curated {result.curated} items",
    )
