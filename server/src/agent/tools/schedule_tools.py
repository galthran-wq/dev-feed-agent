"""User-facing feed-schedule controls (cadence + pause/resume). Main-agent only — sub-agents
must not change user settings. The function docstrings are the LLM-facing tool descriptions."""

from pydantic_ai import RunContext
from src.agent.deps import AgentDeps
from src.models.postgres.connections import ConnectionModel
from src.repositories.connections import ConnectionRepository


def _describe(conn: ConnectionModel) -> str:
    if not conn.feed_enabled:
        return "Your scheduled feed is paused — I won't send it until you resume."
    mins = conn.feed_interval_minutes
    if mins % 1440 == 0:
        every = "day" if mins == 1440 else f"{mins // 1440} days"
    elif mins % 60 == 0:
        every = "hour" if mins == 60 else f"{mins // 60} hours"
    else:
        every = f"{mins} minutes"
    return f"Your feed is delivered about once every {every}."


async def set_feed_schedule(
    ctx: RunContext[AgentDeps], interval_hours: float | None = None, paused: bool | None = None
) -> str:
    """Change how often the user's scheduled feed is delivered, or pause/resume it.

    interval_hours: delivery cadence in hours — e.g. 24 (daily), 12 (twice a day), 3 (every 3
        hours). Minimum 1 hour. Omit to leave the cadence unchanged.
    paused: true to stop scheduled feeds, false to resume. Omit to leave unchanged.
    Call this when the user asks to get the feed more/less often, at some cadence, or to
    stop/resume it. The default cadence is daily.
    """
    interval_minutes = round(interval_hours * 60) if interval_hours is not None else None
    enabled = (not paused) if paused is not None else None
    async with ctx.deps.db_lock:
        conn = await ConnectionRepository(ctx.deps.session).set_schedule(
            ctx.deps.user_id, interval_minutes=interval_minutes, enabled=enabled
        )
    return _describe(conn)


async def get_feed_schedule(ctx: RunContext[AgentDeps]) -> str:
    """Report how often the user's scheduled feed is currently delivered (and whether it's paused)."""
    async with ctx.deps.db_lock:
        conn = await ConnectionRepository(ctx.deps.session).get_or_create(ctx.deps.user_id)
    return _describe(conn)


SCHEDULE_TOOLS = [set_feed_schedule, get_feed_schedule]
