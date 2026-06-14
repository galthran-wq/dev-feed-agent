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


def issue_state() -> str:
    """A signed, short-lived CSRF state token."""
    payload = {
        "nonce": secrets.token_urlsafe(8),
        "exp": datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    return str(jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm))


def verify_state(state: str) -> bool:
    try:
        jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return True
    except JWTError:
        return False


def state_cookie_value(state: str) -> str:
    """The browser-bound cookie value: a SHA-256 hash of the state.

    Storing the hash (not the raw state) keeps the full signed token out of the
    cookie jar while still letting the callback prove the browser is the same one
    that started the flow.
    """
    return hashlib.sha256(state.encode()).hexdigest()


def state_matches_cookie(state: str, cookie_value: str | None) -> bool:
    """Constant-time check that the callback's ``state`` matches the cookie set at login."""
    if not cookie_value:
        return False
    return hmac.compare_digest(state_cookie_value(state), cookie_value)


def cookie_secure() -> bool:
    """Mark the cookie ``Secure`` whenever the app is served over HTTPS.

    Derived from ``APP_BASE_URL`` (the public, nginx-fronted origin); a ``https``
    scheme means TLS terminates at nginx, so the cookie must be HTTPS-only.
    """
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
    """Exchange an authorization code for a GitHub access token."""
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
