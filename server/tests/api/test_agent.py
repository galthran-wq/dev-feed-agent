from httpx import AsyncClient


async def test_get_profile_creates_default(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["github_username"] is None
    assert body["has_github_token"] is False
    assert body["telegram_linked"] is False
    assert body["poll_enabled"] is True


async def test_update_profile(auth_client: AsyncClient) -> None:
    resp = await auth_client.put(
        "/api/agent/profile",
        json={"github_username": "octocat", "github_token": "ghp_secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["github_username"] == "octocat"
    # The token is stored but never echoed back.
    assert body["has_github_token"] is True
    assert "github_token" not in body


async def test_telegram_link_without_bot(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/telegram-link")
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is False
    assert body["bot_configured"] is False
    assert body["url"] is None


async def test_interests_empty(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/interests")
    assert resp.status_code == 200
    assert resp.json()["summary"] == ""


async def test_matches_empty(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/api/agent/matches")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_chat_empty_message_rejected(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/agent/chat", json={"message": "   "})
    assert resp.status_code == 400


async def test_chat_requires_agent(auth_client: AsyncClient) -> None:
    # No OPENROUTER_API_KEY configured in tests -> agent disabled -> 503.
    resp = await auth_client.post("/api/agent/chat", json={"message": "I like Rust"})
    assert resp.status_code == 503


async def test_rebuild_requires_username(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/agent/interests/rebuild")
    assert resp.status_code == 400


async def test_poll_now_without_setup(auth_client: AsyncClient) -> None:
    # No username configured -> discovery returns early without any network calls.
    resp = await auth_client.post("/api/agent/poll-now")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches_sent"] == 0
    assert body["candidates_scanned"] == 0


async def test_agent_endpoints_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/agent/profile")
    assert resp.status_code == 401
