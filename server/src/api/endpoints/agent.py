"""Auth-scoped agent endpoints: status + telegram-link (all the web app needs), plus a
/message debug entry. Real interaction happens in Telegram by talking to the agent."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent.channels import CollectingChannel
from src.core.auth import get_current_user
from src.core.config import settings
from src.core.database import get_postgres_session
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.schemas.agent import (
    MessageRequest,
    MessageResponse,
    StatusResponse,
    TelegramLinkResponse,
)
from src.services.messaging import process_incoming

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


@router.post("/message", response_model=MessageResponse)
async def post_message(
    body: MessageRequest,
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> MessageResponse:
    """Debug mirror of the Telegram path: through process_incoming, agent output buffered and returned."""
    channel = CollectingChannel()
    await process_incoming(channel, session, current_user, body.message)
    return MessageResponse(messages=channel.messages)
