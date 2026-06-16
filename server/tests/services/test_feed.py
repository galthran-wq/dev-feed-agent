from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.models.postgres.connections import ConnectionModel
from src.models.postgres.profiles import ProfileModel
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.services import feed


def test_feed_due_respects_interval_and_pause() -> None:
    now = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    never = ConnectionModel(feed_enabled=True, feed_interval_minutes=1440, last_feed_at=None)
    assert feed.feed_due(never, now) is True  # never fed → due

    fresh = ConnectionModel(feed_enabled=True, feed_interval_minutes=1440, last_feed_at=now - timedelta(minutes=10))
    assert feed.feed_due(fresh, now) is False  # fed 10 min ago, daily cadence → not due

    stale = ConnectionModel(feed_enabled=True, feed_interval_minutes=1440, last_feed_at=now - timedelta(days=2))
    assert feed.feed_due(stale, now) is True  # past the interval → due

    paused = ConnectionModel(feed_enabled=False, feed_interval_minutes=60, last_feed_at=None)
    assert feed.feed_due(paused, now) is False  # paused → never due


async def test_run_for_user_skips_when_not_due(
    feedable_conn: object, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn: ConnectionModel = feedable_conn  # type: ignore[assignment]
    conn.last_feed_at = datetime.now(UTC)  # just fed; default daily cadence → not due
    await db_session.commit()

    async def fake_curate(*a: object, **k: object) -> tuple[int, int]:
        raise AssertionError("must not curate when the feed isn't due")

    monkeypatch.setattr(runtime, "curate_feed", fake_curate)
    result = await feed.run_for_user(db_session, conn)  # type: ignore[arg-type]
    assert result.note == "not due yet"


@pytest.fixture
async def feedable_conn(db_session: AsyncSession, test_user: UserModel) -> object:
    test_user.github_username = "octocat"
    test_user.github_access_token = "gh-token"
    await db_session.commit()
    return await ConnectionRepository(db_session).get_or_create(test_user.id)


async def test_unbuilt_profile_is_built_lazily_then_curated(
    feedable_conn: object, db_session: AsyncSession, test_user: UserModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict = {}

    async def fake_build(kind: str, *, user_id: object, **_: object) -> tuple[str, str]:
        calls["built"] = kind
        # run_subagent owns its own session; simulate the committed build on the test session.
        await ProfileRepository(db_session).mark_built(user_id)
        return "ok", "sid-1"

    async def fake_curate(session: AsyncSession, user: UserModel, channel: object = None) -> tuple[int, int]:
        calls["curated"] = True
        return 2, 1

    monkeypatch.setattr(feed, "run_subagent", fake_build)
    monkeypatch.setattr(runtime, "curate_feed", fake_curate)

    result = await feed.run_for_user(db_session, feedable_conn)  # type: ignore[arg-type]
    assert calls.get("built") == "profile_build"
    assert calls.get("curated") is True
    assert (result.delivered, result.curated) == (1, 2)


async def test_failed_build_skips_curation(
    feedable_conn: object, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_build(kind: str, **_: object) -> tuple[str, str]:
        return "[failed]", "sid"  # never marks the profile built

    async def fake_curate(*a: object, **k: object) -> tuple[int, int]:
        raise AssertionError("curate must not run when the profile build failed")

    monkeypatch.setattr(feed, "run_subagent", fake_build)
    monkeypatch.setattr(runtime, "curate_feed", fake_curate)

    result = await feed.run_for_user(db_session, feedable_conn)  # type: ignore[arg-type]
    assert result.note == "profile build failed"


async def test_built_profile_skips_build(
    feedable_conn: object, db_session: AsyncSession, test_user: UserModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    await ProfileRepository(db_session).mark_built(test_user.id)
    calls: dict = {}

    async def fake_build(*a: object, **k: object) -> tuple[str, str]:
        calls["built"] = True
        return "ok", "sid"

    async def fake_curate(session: AsyncSession, user: UserModel, channel: object = None) -> tuple[int, int]:
        return 1, 1

    monkeypatch.setattr(feed, "run_subagent", fake_build)
    monkeypatch.setattr(runtime, "curate_feed", fake_curate)

    await feed.run_for_user(db_session, feedable_conn)  # type: ignore[arg-type]
    assert "built" not in calls  # already built → no rebuild


async def test_build_on_other_session_is_seen_after_expire(
    feedable_conn: object, db_session: AsyncSession, test_user: UserModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A row exists but isn't built (e.g. a prior partial build). run_for_user's first is_built()
    # loads it into the identity map as built_at=None.
    await ProfileRepository(db_session).set_section(test_user.id, "Summary", "partial")
    calls: dict = {}

    async def fake_build(*a: object, **k: object) -> tuple[str, str]:
        # Simulate the sub-agent committing built_at on ITS OWN session: a Core UPDATE with
        # synchronize_session=False leaves our cached instance stale, exactly like another session.
        await db_session.execute(
            update(ProfileModel)
            .where(ProfileModel.user_id == test_user.id)
            .values(built_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()
        return "ok", "sid"

    async def fake_curate(session: AsyncSession, user: UserModel, channel: object = None) -> tuple[int, int]:
        calls["curated"] = True
        return 1, 1

    monkeypatch.setattr(feed, "run_subagent", fake_build)
    monkeypatch.setattr(runtime, "curate_feed", fake_curate)

    result = await feed.run_for_user(db_session, feedable_conn)  # type: ignore[arg-type]
    # Without expire_all() the stale instance would still read built_at=None → "profile build failed".
    assert calls.get("curated") is True
    assert result.note != "profile build failed"
