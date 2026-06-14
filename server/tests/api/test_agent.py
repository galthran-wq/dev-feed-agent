import pytest
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


async def test_post_message_returns_collected_agent_messages(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The endpoint routes through process_incoming with a CollectingChannel and returns
    # whatever the agent "sent". Stub the core to assert the HTTP collecting contract.
    from src.api.endpoints import agent as agent_ep

    async def fake_process(channel: object, session: object, user: object, text: str) -> None:
        await channel.send(f"echo: {text}")  # type: ignore[union-attr]
        await channel.send("and more")  # type: ignore[union-attr]

    monkeypatch.setattr(agent_ep, "process_incoming", fake_process)

    resp = await auth_client.post("/api/agent/message", json={"message": "yo"})
    assert resp.status_code == 200
    assert resp.json()["messages"] == ["echo: yo", "and more"]


async def test_post_message_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/agent/message", json={"message": "yo"})
    assert resp.status_code == 401


async def test_agent_endpoints_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/agent/status")
    assert resp.status_code == 401
