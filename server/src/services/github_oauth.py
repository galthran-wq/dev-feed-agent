"""GitHub OAuth (authorization-code flow) — the only sign-in path.

The flow yields both an identity (to find-or-create our user) and an access token
we keep for GitHub API calls. CSRF is handled with a short-lived JWT-signed ``state``
(a nonce signed with SECRET_KEY), so no server-side session storage is needed.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

import httpx
import structlog
from jose import JWTError, jwt
from pydantic import BaseModel
from src.core.config import settings

logger = structlog.get_logger()

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_STATE_TTL_MINUTES = 10
_TG_LINK_TTL_MINUTES = 15

#: Name of the HttpOnly cookie that binds the OAuth ``state`` to the browser.
STATE_COOKIE_NAME = "gh_oauth_state"
#: Path-scoped so the cookie is only ever sent to the OAuth endpoints.
STATE_COOKIE_PATH = "/api/auth/github"
#: Short-lived: the GitHub round-trip takes seconds, not minutes.
STATE_COOKIE_MAX_AGE = 600


class GithubUser(BaseModel):
    github_id: str
    username: str
    avatar_url: str | None = None


def issue_state(tg_chat: str | None = None) -> str:
    payload: dict[str, object] = {
        "nonce": secrets.token_urlsafe(8),
        "exp": datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    # When the login was started from Telegram, carry the chat through the (signed) state
    # so the callback can link this chat to the resolved GitHub user.
    if tg_chat:
        payload["tg_chat"] = str(tg_chat)
    return str(jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm))


def verify_state(state: str) -> bool:
    try:
        jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return True
    except JWTError:
        return False


def state_tg_chat(state: str) -> str | None:
    """The Telegram chat id carried in a (verified) state, if the login began in Telegram."""
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    chat = payload.get("tg_chat")
    return str(chat) if chat else None


def issue_tg_link_token(chat_id: str) -> str:
    """Signed, short-lived token the bot puts in the 'Login with GitHub' button URL, so the
    chat id reaching ``/login`` is authentic (not a forged ``?tg=<anyone>``)."""
    payload = {
        "tg_chat": str(chat_id),
        "exp": datetime.now(UTC) + timedelta(minutes=_TG_LINK_TTL_MINUTES),
    }
    return str(jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm))


def read_tg_link_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    chat = payload.get("tg_chat")
    return str(chat) if chat else None


def state_cookie_value(state: str) -> str:
    """Store the hash, not the raw signed token, to keep it out of the cookie jar."""
    return hashlib.sha256(state.encode()).hexdigest()


def state_matches_cookie(state: str, cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    return hmac.compare_digest(state_cookie_value(state), cookie_value)


def cookie_secure() -> bool:
    # APP_BASE_URL is the public nginx-fronted origin; https there means TLS terminates at nginx.
    return urlparse(settings.app_base_url).scheme == "https"


def build_authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": settings.github_oauth_scopes,
            "state": state,
        }
    )
    return f"{_AUTHORIZE_URL}?{query}"


async def exchange_code(code: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ValueError(f"GitHub token exchange failed: {data.get('error_description') or data.get('error')}")
    return str(token)


async def fetch_github_user(token: str) -> GithubUser:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            _USER_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
    return GithubUser(github_id=str(data["id"]), username=data["login"], avatar_url=data.get("avatar_url"))
