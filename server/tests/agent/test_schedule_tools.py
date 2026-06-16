import types

from sqlalchemy.ext.asyncio import AsyncSession
from src.agent.deps import AgentDeps
from src.agent.tools import BASE_TOOLS, MAIN_TOOLS
from src.agent.tools.schedule_tools import get_feed_schedule, set_feed_schedule
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository


def _ctx(db_session: AsyncSession, user: UserModel) -> object:
    # The tools only touch ctx.deps.{session,user_id,db_lock} — a lightweight stand-in suffices.
    return types.SimpleNamespace(deps=AgentDeps(session=db_session, user_id=user.id))


async def test_set_feed_schedule_updates_interval_and_pause(db_session: AsyncSession, test_user: UserModel) -> None:
    ctx = _ctx(db_session, test_user)

    msg = await set_feed_schedule(ctx, interval_hours=3)  # type: ignore[arg-type]
    conn = await ConnectionRepository(db_session).get_by_user_id(test_user.id)
    assert conn is not None and conn.feed_interval_minutes == 180
    assert "3 hours" in msg

    await set_feed_schedule(ctx, paused=True)  # type: ignore[arg-type]
    conn = await ConnectionRepository(db_session).get_by_user_id(test_user.id)
    assert conn is not None and conn.feed_enabled is False
    # interval preserved when only pausing
    assert conn.feed_interval_minutes == 180

    resume = await set_feed_schedule(ctx, paused=False)  # type: ignore[arg-type]
    assert "paused" not in resume.lower()


async def test_set_feed_schedule_clamps_sub_hour(db_session: AsyncSession, test_user: UserModel) -> None:
    await set_feed_schedule(_ctx(db_session, test_user), interval_hours=0.5)  # type: ignore[arg-type]
    conn = await ConnectionRepository(db_session).get_by_user_id(test_user.id)
    assert conn is not None and conn.feed_interval_minutes == 60  # clamped up to 1h


async def test_get_feed_schedule_reports_default(db_session: AsyncSession, test_user: UserModel) -> None:
    msg = await get_feed_schedule(_ctx(db_session, test_user))  # type: ignore[arg-type]
    assert "day" in msg.lower()  # default daily


def test_schedule_tools_are_main_only() -> None:
    assert set_feed_schedule in MAIN_TOOLS
    assert set_feed_schedule not in BASE_TOOLS  # sub-agents can't change user settings
