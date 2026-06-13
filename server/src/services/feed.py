"""Per-user feed pass: curate (agent) → deliver to Telegram → mark fed.

Curation records items for dedup regardless of delivery; a delivery failure for one
item never aborts the rest of the user's feed.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.core.config import settings
from src.models.postgres.connections import ConnectionModel
from src.repositories.connections import ConnectionRepository
from src.repositories.profiles import ProfileRepository
from src.repositories.users import UserRepository
from src.services import notifier

logger = structlog.get_logger()


class FeedResult:
    def __init__(self, delivered: int, curated: int, note: str = "") -> None:
        self.delivered = delivered
        self.curated = curated
        self.note = note


async def run_for_user(session: AsyncSession, conn: ConnectionModel, *, deliver: bool = True) -> FeedResult:
    log = logger.bind(user_id=str(conn.user_id))

    user = await UserRepository(session).get_user(conn.user_id)
    if user is None or not user.github_username:
        return FeedResult(0, 0, "no github identity")
    if not await ProfileRepository(session).is_built(conn.user_id):
        return FeedResult(0, 0, "profile not built yet")

    items = await runtime.curate_feed(session, user)
    await ConnectionRepository(session).mark_fed(conn)
    if not items:
        return FeedResult(0, 0, "no new matches")

    delivered = 0
    if deliver and conn.telegram_chat_id and settings.telegram_enabled:
        for item in items:
            try:
                await notifier.send_text(conn.telegram_chat_id, notifier.format_feed_item(item))
                delivered += 1
            except Exception as exc:  # never let one delivery failure abort the feed
                log.warning("feed_delivery_failed", error=str(exc))

    log.info("feed_pass_done", curated=len(items), delivered=delivered)
    return FeedResult(delivered, len(items))
