from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.agent import runtime
from src.agent.channels import CollectingChannel
from src.core import config
from src.models.postgres.users import UserModel
from src.services import messaging


@pytest.fixture
def _wire(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Point process_incoming's own-session at the test engine, enable the agent, and
    stub the runtime entry points so we assert dispatch (not LLM behavior)."""
    maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(messaging, "AsyncSessionLocal", maker)
    monkeypatch.setattr(config.settings, "openrouter_api_key", "test-key")  # agent_enabled

    calls: dict = {}

    async def fake_reset(session: AsyncSession, user: UserModel) -> None:
        calls["reset"] = user.id

    async def fake_compact(session: AsyncSession, user: UserModel) -> str:
        calls["compact"] = user.id
        return "carried summary"

    async def fake_build(user_id: object, channel: object = None) -> None:
        calls["build"] = user_id

    async def fake_chat(session: AsyncSession, user: UserModel, text: str, channel: object = None) -> None:
        calls["chat"] = text
        await channel.send("agent reply")  # type: ignore[union-attr]

    monkeypatch.setattr(runtime, "reset", fake_reset)
    monkeypatch.setattr(runtime, "compact", fake_compact)
    monkeypatch.setattr(runtime, "build_profile_safe", fake_build)
    monkeypatch.setattr(runtime, "chat", fake_chat)
    return calls


async def test_dispatch_reset(_wire: dict, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, test_user.id, "/reset")
    assert _wire["reset"] == test_user.id
    assert any("Cleared" in m for m in ch.messages)


async def test_dispatch_compact(_wire: dict, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, test_user.id, "/compact")
    assert _wire["compact"] == test_user.id
    assert any("carried summary" in m for m in ch.messages)


async def test_dispatch_init(_wire: dict, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, test_user.id, "/init")
    assert _wire["build"] == test_user.id


async def test_dispatch_free_text_goes_to_chat(_wire: dict, test_user: UserModel) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, test_user.id, "any rust news?")
    assert _wire["chat"] == "any rust news?"
    assert ch.messages == ["agent reply"]


async def test_unknown_user_is_told_to_link(_wire: dict) -> None:
    ch = CollectingChannel()
    await messaging.process_incoming(ch, uuid4(), "hi")
    assert any("isn't linked" in m for m in ch.messages)
