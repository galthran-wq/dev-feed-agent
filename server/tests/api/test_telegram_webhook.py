import asyncio

import pytest
from httpx import AsyncClient
from src.api.endpoints import telegram as tg_ep
from src.core import config

_SECRET = "test-webhook-secret"
_HDR = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "telegram_webhook_secret", _SECRET)


def _update(update_id: int, text: str = "hi", chat_id: int = 5) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


async def test_rejects_missing_or_wrong_secret(client: AsyncClient) -> None:
    r = await client.post("/api/telegram/webhook", json=_update(1))
    assert r.status_code == 403
    r = await client.post("/api/telegram/webhook", json=_update(1), headers={_HDR: "nope"})
    assert r.status_code == 403


async def test_ignores_non_message_update(client: AsyncClient) -> None:
    r = await client.post("/api/telegram/webhook", json={"update_id": 7}, headers={_HDR: _SECRET})
    assert r.status_code == 200


async def test_processes_once_and_dedups(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    async def fake_handle(chat_id: str, text: str, quoted: str | None = None) -> None:
        calls.append((chat_id, text, quoted))

    monkeypatch.setattr(tg_ep, "handle_update", fake_handle)

    payload = _update(42, text="hello")
    r1 = await client.post("/api/telegram/webhook", json=payload, headers={_HDR: _SECRET})
    r2 = await client.post("/api/telegram/webhook", json=payload, headers={_HDR: _SECRET})
    assert r1.status_code == 200 and r2.status_code == 200

    await asyncio.sleep(0.05)  # let the fast-acked background task run
    # Same update_id delivered twice → handled exactly once.
    assert calls == [("5", "hello", None)]


async def test_forwards_quote_context(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_handle(chat_id: str, text: str, quoted: str | None = None) -> None:
        seen["args"] = (chat_id, text, quoted)

    monkeypatch.setattr(tg_ep, "handle_update", fake_handle)

    payload = {
        "update_id": 99,
        "message": {
            "chat": {"id": 5},
            "text": "is it better than insightface?",
            "quote": {"text": "UniFace — unified face analysis"},
        },
    }
    await client.post("/api/telegram/webhook", json=payload, headers={_HDR: _SECRET})
    await asyncio.sleep(0.05)
    assert seen["args"] == ("5", "is it better than insightface?", "UniFace — unified face analysis")
