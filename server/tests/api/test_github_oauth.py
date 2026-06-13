from httpx import AsyncClient
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


async def test_login_disabled_without_oauth_config(client: AsyncClient) -> None:
    # No GITHUB_OAUTH_CLIENT_ID/SECRET in tests -> OAuth disabled -> 503.
    resp = await client.get("/api/auth/github/login", follow_redirects=False)
    assert resp.status_code == 503
