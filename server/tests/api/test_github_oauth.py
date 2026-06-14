import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.models.postgres.users import UserModel
from src.services import github_oauth


def test_state_roundtrip() -> None:
    state = github_oauth.issue_state()
    assert github_oauth.verify_state(state) is True


def test_state_rejects_garbage() -> None:
    assert github_oauth.verify_state("not-a-real-token") is False


def test_authorize_url_contains_state_and_redirect() -> None:
    url = github_oauth.build_authorize_url("STATE123")
    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "state=STATE123" in url
    assert "redirect_uri=" in url
    assert "scope=" in url


def test_state_cookie_value_is_sha256_hash() -> None:
    state = github_oauth.issue_state()
    value = github_oauth.state_cookie_value(state)
    # Hash, not the raw token: hex, 64 chars, and not equal to the state itself.
    assert len(value) == 64
    assert value != state
    assert github_oauth.state_matches_cookie(state, value) is True
    assert github_oauth.state_matches_cookie(state, "deadbeef") is False
    assert github_oauth.state_matches_cookie(state, None) is False


def test_cookie_secure_follows_app_base_url_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_base_url", "https://feed.example.com")
    assert github_oauth.cookie_secure() is True
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:5677")
    assert github_oauth.cookie_secure() is False


async def test_login_disabled_without_oauth_config(client: AsyncClient) -> None:
    # No GITHUB_OAUTH_CLIENT_ID/SECRET in tests -> OAuth disabled -> 503.
    resp = await client.get("/api/auth/github/login", follow_redirects=False)
    assert resp.status_code == 503


def _enable_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "github_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "csecret")


async def test_login_sets_httponly_state_cookie(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_oauth(monkeypatch)
    resp = await client.get("/api/auth/github/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "github.com/login/oauth/authorize" in resp.headers["location"]

    set_cookie = resp.headers.get("set-cookie", "")
    lowered = set_cookie.lower()
    assert github_oauth.STATE_COOKIE_NAME in set_cookie
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert f"path={github_oauth.STATE_COOKIE_PATH}".lower() in lowered
    # Local/http default -> not Secure.
    assert "secure" not in lowered


async def test_callback_rejected_without_cookie(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)

    async def _boom(*_a: object, **_k: object) -> object:  # pragma: no cover - must not run
        raise AssertionError("exchange_code should not run when the state cookie is missing")

    monkeypatch.setattr(github_oauth, "exchange_code", _boom)

    state = github_oauth.issue_state()
    # Valid signed state, but the browser presents NO state cookie.
    resp = await client.get(f"/api/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 400

    count = (await db_session.execute(select(func.count()).select_from(UserModel))).scalar_one()
    assert count == 0


async def test_callback_rejected_on_cookie_mismatch(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)

    async def _boom(*_a: object, **_k: object) -> object:  # pragma: no cover - must not run
        raise AssertionError("exchange_code should not run on cookie mismatch")

    monkeypatch.setattr(github_oauth, "exchange_code", _boom)

    state = github_oauth.issue_state()
    other_state = github_oauth.issue_state()
    client.cookies.set(
        github_oauth.STATE_COOKIE_NAME,
        github_oauth.state_cookie_value(other_state),  # cookie for a DIFFERENT state
    )
    resp = await client.get(f"/api/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 400

    count = (await db_session.execute(select(func.count()).select_from(UserModel))).scalar_one()
    assert count == 0


async def test_callback_succeeds_with_matching_cookie_and_clears_it(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)

    async def _fake_exchange(code: str) -> str:
        assert code == "the-code"
        return "gh-token"

    async def _fake_user(token: str) -> github_oauth.GithubUser:
        assert token == "gh-token"
        return github_oauth.GithubUser(github_id="42", username="octocat", avatar_url=None)

    monkeypatch.setattr(github_oauth, "exchange_code", _fake_exchange)
    monkeypatch.setattr(github_oauth, "fetch_github_user", _fake_user)

    state = github_oauth.issue_state()
    client.cookies.set(
        github_oauth.STATE_COOKIE_NAME,
        github_oauth.state_cookie_value(state),
    )
    resp = await client.get(f"/api/auth/github/callback?code=the-code&state={state}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/auth/callback#token=" in resp.headers["location"]

    # Single-use: the cookie is cleared on the success response.
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert github_oauth.STATE_COOKIE_NAME in set_cookie
    assert ("max-age=0" in set_cookie) or ("expires=" in set_cookie)

    user = (await db_session.execute(select(UserModel).where(UserModel.github_id == "42"))).scalar_one()
    assert user.github_username == "octocat"
