import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.agent.channels import CollectingChannel
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.services import channels


@pytest.fixture
def _wire(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> CollectingChannel:
    """Point handle_update's own-session at the test engine and capture what it sends."""
    maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(channels, "AsyncSessionLocal", maker)
    ch = CollectingChannel()
    monkeypatch.setattr(channels, "TelegramChannel", lambda chat_id: ch)
    return ch


async def test_handle_update_swallows_errors(_wire: CollectingChannel, monkeypatch: pytest.MonkeyPatch) -> None:
    """handle_update runs detached from the (already-acked) webhook, so a failure must be
    caught and surfaced to the user, never left to die in the event loop."""

    async def boom(channel: object, chat_id: str, code: str) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(channels, "_handle_start", boom)

    await channels.handle_update("5", "/start somecode")  # must not raise
    assert any("went wrong" in m for m in _wire.messages)


async def test_unlinked_chat_is_told_to_link(_wire: CollectingChannel) -> None:
    # No connection for this chat_id → the Telegram layer (not process_incoming) owns this.
    await channels.handle_update("999", "hello")
    assert any("isn't linked" in m for m in _wire.messages)


async def test_linked_chat_reaches_process_incoming(
    _wire: CollectingChannel, db_session: AsyncSession, test_user: UserModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = ConnectionRepository(db_session)
    conn = await repo.get_or_create(test_user.id)
    await repo.link_telegram(conn.telegram_link_code, "5")

    seen: dict = {}

    async def fake_process(channel: object, session: AsyncSession, user: UserModel, text: str) -> None:
        seen["user_id"] = user.id
        seen["text"] = text

    monkeypatch.setattr(channels, "process_incoming", fake_process)

    await channels.handle_update("5", "any rust news?")
    assert seen == {"user_id": test_user.id, "text": "any rust news?"}
