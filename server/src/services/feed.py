"""Per-user feed pass: curate via the agent (it delivers through its channel) → mark fed.
``channel=None`` curates without delivering (dry run / tests)."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import Channel
from src.agent.subagents import run_subagent
from src.models.postgres.connections import ConnectionModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.users import UserRepository

logger = structlog.get_logger()


class FeedResult:
    def __init__(self, delivered: int, curated: int, note: str = "") -> None:
        self.delivered = delivered
        self.curated = curated
        self.note = note


async def run_for_user(session: AsyncSession, conn: ConnectionModel, *, channel: Channel | None = None) -> FeedResult:
    log = logger.bind(user_id=str(conn.user_id))

    user = await UserRepository(session).get_user(conn.user_id)
    if user is None or not user.github_username:
        return FeedResult(0, 0, "no github identity")

    profiles = ProfileRepository(session)
    if not await profiles.is_built(conn.user_id):
        # Profile is built lazily (no OAuth pre-warm). A user who linked Telegram but never
        # chatted has no profile yet — build it here (silently) so the scheduled feed still
        # reaches them, via the same single build path the chat agent uses.
        await run_subagent(
            "profile_build",
            session=session,
            user_id=user.id,
            github_token=user.github_access_token,
            github_username=user.github_username,
            channel=None,
        )
        if not await profiles.is_built(conn.user_id):
            return FeedResult(0, 0, "profile build failed")

    new_items, sent = await runtime.curate_feed(session, user, channel)
    await ConnectionRepository(session).mark_fed(conn)
    if new_items == 0:
        return FeedResult(0, 0, "no new matches")

    log.info("feed_pass_done", curated=new_items, delivered=sent)
    return FeedResult(sent, new_items)
