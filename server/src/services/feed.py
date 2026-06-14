"""Per-user feed pass: curate (agent) → the agent delivers via its channel → mark fed.

The agent records items for dedup and sends the digest itself through ``send_message``
(the ``channel``). Passing ``channel=None`` curates without delivering (dry run / tests).
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.agent.channels import Channel
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
    if not await ProfileRepository(session).is_built(conn.user_id):
        return FeedResult(0, 0, "profile not built yet")

    new_items = await runtime.curate_feed(session, user, channel)
    await ConnectionRepository(session).mark_fed(conn)
    if new_items == 0:
        return FeedResult(0, 0, "no new matches")

    # The agent delivers via the channel itself; "delivered" reflects that a channel was
    # available to send through.
    delivered = new_items if channel is not None else 0
    log.info("feed_pass_done", curated=new_items, delivered=delivered)
    return FeedResult(delivered, new_items)
