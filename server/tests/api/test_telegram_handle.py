import pytest
from src.agent.channels import CollectingChannel
from src.api.endpoints import telegram as tg_ep


async def test_handle_update_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """handle_update runs detached from the (already-acked) webhook, so a failure must be
    caught and surfaced to the user, never left to die in the event loop."""
    ch = CollectingChannel()
    monkeypatch.setattr(tg_ep, "TelegramChannel", lambda chat_id: ch)

    async def boom(channel: object, chat_id: str, code: str) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(tg_ep, "_handle_start", boom)

    # Must not raise.
    await tg_ep.handle_update("5", "/start somecode")
    assert any("went wrong" in m for m in ch.messages)
