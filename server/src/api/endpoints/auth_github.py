"""GitHub OAuth sign-in endpoints. On success we mint the same JWT the rest of the
app uses, and on first connect we kick off the profile build in the background."""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.auth import create_token_for_user
from src.core.config import settings
from src.core.database import get_postgres_session
from src.core.exceptions import AppError
from src.repositories.connections import ConnectionRepository
from src.repositories.users import UserRepository
from src.services import github_oauth

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth/github", tags=["auth"])


def _clear_state_cookie(response: RedirectResponse) -> None:
    """Single-use: drop the state cookie regardless of outcome."""
    response.delete_cookie(
        github_oauth.STATE_COOKIE_NAME,
        path=github_oauth.STATE_COOKIE_PATH,
    )


@router.get("/login")
async def github_login() -> RedirectResponse:
    if not settings.github_oauth_enabled:
        raise AppError(status_code=503, detail="GitHub OAuth is not configured")
    state = github_oauth.issue_state()
    response = RedirectResponse(github_oauth.build_authorize_url(state))
    # Bind the state to this browser: only a callback carrying the matching cookie
    # is honoured, which closes login-CSRF. HttpOnly keeps it out of JS; SameSite=Lax
    # still rides along on GitHub's top-level redirect back to us.
    response.set_cookie(
        github_oauth.STATE_COOKIE_NAME,
        github_oauth.state_cookie_value(state),
        max_age=github_oauth.STATE_COOKIE_MAX_AGE,
        path=github_oauth.STATE_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=github_oauth.cookie_secure(),
    )
    return response


@router.get("/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    session: AsyncSession = Depends(get_postgres_session),
) -> RedirectResponse:
    if not settings.github_oauth_enabled:
        raise AppError(status_code=503, detail="GitHub OAuth is not configured")

    # Browser binding (anti-CSRF) first, then the standalone signature/expiry check
    # (defense in depth). A rejected attempt leaves the cookie in place, but it is
    # path-scoped, short-lived, and single-use-by-binding, so it can't be replayed;
    # the cookie is actively cleared on the success path below.
    cookie = request.cookies.get(github_oauth.STATE_COOKIE_NAME)
    if not github_oauth.state_matches_cookie(state, cookie) or not github_oauth.verify_state(state):
        logger.warning("github_oauth_state_rejected", has_cookie=bool(cookie))
        # AppError yields a clean 400; the cookie is path-scoped, short-lived and
        # single-use-by-binding, so a mismatched attempt can't be replayed anyway.
        raise AppError(status_code=400, detail="Invalid or expired OAuth state")

    try:
        token = await github_oauth.exchange_code(code)
        gh_user = await github_oauth.fetch_github_user(token)
    except Exception as exc:
        logger.warning("github_oauth_failed", error=str(exc))
        raise AppError(status_code=400, detail="GitHub authorization failed") from exc

    user, created = await UserRepository(session).upsert_github_user(
        gh_user.github_id, gh_user.username, token, gh_user.avatar_url
    )
    # Every user needs a connection row (holds the Telegram link code).
    await ConnectionRepository(session).get_or_create(user.id)

    if created and settings.agent_enabled:
        # Fire-and-forget the initial profile build; the user lands on a "building" state.
        from src.agent import runtime

        asyncio.create_task(runtime.build_profile_safe(user.id))  # noqa: RUF006

    jwt_token = create_token_for_user(user)
    # Deliver the JWT in the URL fragment, not the query string: fragments are never
    # sent to the server (so they stay out of access logs) nor leaked via Referer.
    redirect = f"{settings.app_base_url.rstrip('/')}/auth/callback#token={jwt_token}"
    response = RedirectResponse(redirect)
    _clear_state_cookie(response)  # single-use
    return response
