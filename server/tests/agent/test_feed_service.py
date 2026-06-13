"""Feed pass atomicity: items stay "pending" until a Telegram send succeeds.

A delivery failure must leave the shown-ledger as "pending" so the next pass retries
(via the leftover sweep); only a successful send flips rows to "delivered".
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.connections import ConnectionModel
from src.models.postgres.users import UserModel
from src.repositories.feed_items import FeedItemRepository
from src.repositories.profiles import ProfileRepository
from src.services import feed


@pytest.fixture
async def feedable_conn(db_session: AsyncSession) -> AsyncIterator[ConnectionModel]:
    user = UserModel(email="feed@example.com", password_hash="x", is_verified=True, github_username="octocat")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    await ProfileRepository(db_session).mark_built(user.id)

    conn = ConnectionModel(user_id=user.id, telegram_chat_id="chat-1")
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)
    yield conn


async def _record(session: AsyncSession, user_id, key) -> None:  # type: ignore[no-untyped-def]
    """Simulate record_feed_items: a pending row plus the key curate_feed returns."""
    await FeedItemRepository(session).add(
        user_id,
        source=key[0],
        item_type="repo",
        external_id=key[1],
        url=f"https://example.com/{key[1]}",
        title=f"Item {key[1]}",
    )


async def test_delivery_success_marks_delivered(
    db_session: AsyncSession, feedable_conn: ConnectionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.core.config.settings.telegram_bot_token", "token", raising=False)

    key = ("github", "owner/name")

    async def fake_curate(session, user):  # type: ignore[no-untyped-def]
        await _record(session, feedable_conn.user_id, key)
        return "Here is your feed", [key]

    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id, text):  # type: ignore[no-untyped-def]
        sent.append((chat_id, text))

    monkeypatch.setattr(feed.runtime, "curate_feed", fake_curate)
    monkeypatch.setattr(feed.notifier, "send_text", fake_send)

    result = await feed.run_for_user(db_session, feedable_conn)

    assert result.delivered == 1
    assert sent == [("chat-1", "Here is your feed")]
    # The row was flipped pending -> delivered, so nothing is left pending.
    assert await FeedItemRepository(db_session).list_pending(feedable_conn.user_id) == []


async def test_delivery_failure_leaves_pending(
    db_session: AsyncSession, feedable_conn: ConnectionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.core.config.settings.telegram_bot_token", "token", raising=False)

    key = ("github", "owner/name")

    async def fake_curate(session, user):  # type: ignore[no-untyped-def]
        await _record(session, feedable_conn.user_id, key)
        return "Here is your feed", [key]

    async def boom(chat_id, text):  # type: ignore[no-untyped-def]
        raise RuntimeError("telegram down")

    monkeypatch.setattr(feed.runtime, "curate_feed", fake_curate)
    monkeypatch.setattr(feed.notifier, "send_text", boom)

    result = await feed.run_for_user(db_session, feedable_conn)

    assert result.delivered == 0
    assert result.curated == 1
    # Delivery failed -> the item is still pending and will be retried next pass.
    pending = await FeedItemRepository(db_session).list_pending(feedable_conn.user_id)
    assert {(p.source, p.external_id) for p in pending} == {key}


async def test_leftover_sweep_redelivers(
    db_session: AsyncSession, feedable_conn: ConnectionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.core.config.settings.telegram_bot_token", "token", raising=False)

    # A leftover from a prior failed send.
    leftover = ("github", "left/over")
    await _record(db_session, feedable_conn.user_id, leftover)

    async def fake_curate(session, user):  # type: ignore[no-untyped-def]
        return "nothing new", []  # no fresh items this run

    sent: list[str] = []

    async def fake_send(chat_id, text):  # type: ignore[no-untyped-def]
        sent.append(text)

    monkeypatch.setattr(feed.runtime, "curate_feed", fake_curate)
    monkeypatch.setattr(feed.notifier, "send_text", fake_send)

    result = await feed.run_for_user(db_session, feedable_conn)

    assert result.delivered == 1  # the leftover got delivered
    assert len(sent) == 1
    assert "left/over" in sent[0]
    assert await FeedItemRepository(db_session).list_pending(feedable_conn.user_id) == []


async def test_empty_digest_is_not_sent(
    db_session: AsyncSession, feedable_conn: ConnectionModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.core.config.settings.telegram_bot_token", "token", raising=False)

    key = ("github", "owner/name")

    async def fake_curate(session, user):  # type: ignore[no-untyped-def]
        await _record(session, feedable_conn.user_id, key)
        return "   \n  ", [key]  # whitespace-only digest

    sent: list[str] = []

    async def fake_send(chat_id, text):  # type: ignore[no-untyped-def]
        sent.append(text)

    monkeypatch.setattr(feed.runtime, "curate_feed", fake_curate)
    monkeypatch.setattr(feed.notifier, "send_text", fake_send)

    result = await feed.run_for_user(db_session, feedable_conn)

    assert sent == []  # nothing sent
    assert result.delivered == 0
    # Nothing marked delivered -> item stays pending for a future retry.
    pending = await FeedItemRepository(db_session).list_pending(feedable_conn.user_id)
    assert {(p.source, p.external_id) for p in pending} == {key}
