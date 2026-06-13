from httpx import AsyncClient


async def test_status_creates_connection(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/status")
    assert resp.status_code == 200
    body = resp.json()
    # The email/password test user has no GitHub identity or profile yet.
    assert body["github_connected"] is False
    assert body["telegram_linked"] is False
    assert body["profile_built"] is False


async def test_telegram_link_without_bot(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/telegram-link")
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is False
    assert body["bot_configured"] is False
    assert body["url"] is None


async def test_rebuild_requires_github(auth_client: AsyncClient) -> None:
    # No github_username on the user -> 400 before any agent work.
    resp = await auth_client.post("/api/agent/rebuild")
    assert resp.status_code == 400


async def test_poll_now_without_setup(auth_client: AsyncClient) -> None:
    # No github identity -> the feed pass returns early, no network calls.
    resp = await auth_client.post("/api/agent/poll-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivered"] == 0
    assert body["curated"] == 0


async def test_agent_endpoints_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/agent/status")
    assert resp.status_code == 401
