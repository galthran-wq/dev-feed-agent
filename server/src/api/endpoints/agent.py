from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.auth import get_current_user
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.models.postgres.github_profiles import GithubProfileModel
from src.models.postgres.users import UserModel
from src.repositories.chat_messages import ChatMessageRepository
from src.repositories.github_profiles import GithubProfileRepository
from src.repositories.interest_profiles import InterestProfileRepository
from src.repositories.sent_issues import SentIssueRepository
from src.schemas.agent import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    GithubProfileResponse,
    InterestProfileResponse,
    PollNowResponse,
    RebuildProfileResponse,
    SentIssueResponse,
    TelegramLinkResponse,
    UpdateGithubProfileRequest,
)
from src.services import discovery_service, interest_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _profile_response(profile: GithubProfileModel) -> GithubProfileResponse:
    return GithubProfileResponse(
        github_username=profile.github_username,
        has_github_token=bool(profile.github_token),
        telegram_linked=bool(profile.telegram_chat_id),
        poll_enabled=profile.poll_enabled,
        last_polled_at=profile.last_polled_at,
    )


@router.get("/profile", response_model=GithubProfileResponse)
async def get_profile(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> GithubProfileResponse:
    profile = await GithubProfileRepository(session).get_or_create(current_user.id)
    return _profile_response(profile)


@router.put("/profile", response_model=GithubProfileResponse)
async def update_profile(
    request: UpdateGithubProfileRequest,
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> GithubProfileResponse:
    profile = await GithubProfileRepository(session).update_settings(
        current_user.id,
        github_username=request.github_username,
        github_token=request.github_token,
        poll_enabled=request.poll_enabled,
    )
    return _profile_response(profile)


@router.get("/interests", response_model=InterestProfileResponse)
async def get_interests(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> InterestProfileResponse:
    interests = await InterestProfileRepository(session).get_by_user_id(current_user.id)
    if interests is None:
        return InterestProfileResponse()
    return InterestProfileResponse.model_validate(interests)


@router.post("/interests/rebuild", response_model=RebuildProfileResponse)
async def rebuild_interests(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> RebuildProfileResponse:
    profile = await GithubProfileRepository(session).get_or_create(current_user.id)
    if not profile.github_username:
        raise AppError(status_code=400, detail="Set your GitHub username first")
    stored, repos_scanned = await interest_service.rebuild_profile(
        session, current_user.id, profile.github_username, profile.github_token
    )
    return RebuildProfileResponse(interests=InterestProfileResponse.model_validate(stored), repos_scanned=repos_scanned)


@router.get("/telegram-link", response_model=TelegramLinkResponse)
async def get_telegram_link(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> TelegramLinkResponse:
    profile = await GithubProfileRepository(session).get_or_create(current_user.id)
    bot_configured = settings.telegram_enabled and bool(settings.telegram_bot_username)
    url = None
    if bot_configured:
        url = f"https://t.me/{settings.telegram_bot_username}?start={profile.telegram_link_code}"
    return TelegramLinkResponse(linked=bool(profile.telegram_chat_id), url=url, bot_configured=bot_configured)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> ChatResponse:
    if not request.message.strip():
        raise AppError(status_code=400, detail="Message cannot be empty")
    result = await interest_service.refine_for_user(session, current_user.id, request.message)
    return ChatResponse(
        reply=result.reply,
        interests=InterestProfileResponse(
            summary=result.summary,
            languages=result.languages,
            topics=result.topics,
            keywords=result.keywords,
        ),
    )


@router.get("/chat/history", response_model=list[ChatMessageResponse])
async def chat_history(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> list[ChatMessageResponse]:
    messages = await ChatMessageRepository(session).list_recent(current_user.id, limit=50)
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.get("/matches", response_model=list[SentIssueResponse])
async def list_matches(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> list[SentIssueResponse]:
    matches = await SentIssueRepository(session).list_recent(current_user.id, limit=50)
    return [SentIssueResponse.model_validate(m) for m in matches]


@router.post("/poll-now", response_model=PollNowResponse)
async def poll_now(
    current_user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_postgres_session),
) -> PollNowResponse:
    profile = await GithubProfileRepository(session).get_or_create(current_user.id)
    result = await discovery_service.run_for_user(session, profile)
    note = result.note or f"Scanned {result.candidates_scanned} candidates"
    return PollNowResponse(matches_sent=result.matches_sent, candidates_scanned=result.candidates_scanned, message=note)
