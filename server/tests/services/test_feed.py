import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.services import feed


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
