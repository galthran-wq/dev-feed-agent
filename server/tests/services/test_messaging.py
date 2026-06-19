import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import CollectingChannel
from src.models.postgres.users import UserModel
from src.services import messaging


@pytest.fixture
def _wire(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub the runtime entry points so we assert dispatch, not LLM behavior."""
    calls: dict = {}

    async def fake_reset(session: AsyncSession, user: UserModel) -> None:
        calls["reset"] = user.id

    async def fake_compact(session: AsyncSession, user: UserModel) -> str:
        calls["compact"] = user.id
        return "carried summary"

    async def fake_chat(session: AsyncSession, user: UserModel, text: str, channel: object = None) -> None:
        calls["chat"] = text
        await channel.send("agent reply")  # type: ignore[union-attr]

    monkeypatch.setattr(runtime, "reset", fake_reset)
    monkeypatch.setattr(runtime, "compact", fake_compact)
    monkeypatch.setattr(runtime, "chat", fake_chat)
    return calls


async def test_dispatch_reset(_wire: dict, db_session: AsyncSession, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, db_session, test_user, "/reset")
    assert _wire["reset"] == test_user.id
    assert any("Cleared" in m for m in ch.messages)


async def test_dispatch_compact(_wire: dict, db_session: AsyncSession, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, db_session, test_user, "/compact")
    assert _wire["compact"] == test_user.id
    assert any("carried summary" in m for m in ch.messages)


async def test_dispatch_free_text_goes_to_chat(_wire: dict, db_session: AsyncSession, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, db_session, test_user, "any rust news?")
    assert _wire["chat"] == "any rust news?"
    assert ch.messages == ["agent reply"]


async def test_chat_failure_is_caught_and_apologized(
    _wire: dict, db_session: AsyncSession, test_user: UserModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(runtime, "chat", boom)
    ch = CollectingChannel()
    # Must not raise; the user gets the shared apology.
    await messaging.process_incoming(ch, db_session, test_user, "hi")
    assert ch.messages == [messaging.GENERIC_ERROR]
