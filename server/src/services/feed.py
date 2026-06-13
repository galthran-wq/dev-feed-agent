"""Per-user feed pass: re-deliver leftovers → curate (agent) → deliver → mark delivered.

Curation records items as "pending" for dedup regardless of delivery; only a successful
Telegram send flips them to "delivered". A delivery failure leaves them "pending" so the
next pass retries them (and never re-curates them as new). A delivery failure for one
pass never aborts the rest of the user's feed.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import runtime
from src.core.config import settings
from src.models.postgres.connections import ConnectionModel
from src.models.postgres.feed_items import FeedItemModel
from src.repositories.connections import ConnectionRepository
from src.repositories.feed_items import FeedItemRepository
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

    feed_repo = FeedItemRepository(session)
    chat_id = conn.telegram_chat_id
    can_deliver = bool(deliver and chat_id and settings.telegram_enabled)

    # 1) Leftover sweep: re-deliver anything still "pending" from a prior failed send so it's
    #    never lost. These were already excluded from this run's curation by filter_unseen.
    leftover_delivered = 0
    if can_deliver and chat_id is not None:
        leftovers = await feed_repo.list_pending(conn.user_id)
        if leftovers:
            keys = [(i.source, i.external_id) for i in leftovers]
            if await _deliver(chat_id, _leftover_digest(leftovers)):
                leftover_delivered = await feed_repo.mark_delivered(conn.user_id, keys)

    # 2) Curate this run's fresh items (recorded as "pending").
    digest, recorded_keys = await runtime.curate_feed(session, user)
    await ConnectionRepository(session).mark_fed(conn)
    new_items = len(recorded_keys)
    if new_items == 0:
        if leftover_delivered:
            return FeedResult(leftover_delivered, 0, "delivered leftovers only")
        return FeedResult(0, 0, "no new matches")

    # 3) Deliver fresh digest; flip pending → delivered only on success. On failure the rows
    #    stay "pending" and the next pass's leftover sweep retries them.
    delivered = 0
    if can_deliver and chat_id is not None and await _deliver(chat_id, digest):
        delivered = await feed_repo.mark_delivered(conn.user_id, recorded_keys)

    log.info("feed_pass_done", curated=new_items, delivered=delivered, leftovers=leftover_delivered)
    return FeedResult(delivered + leftover_delivered, new_items)


def _leftover_digest(items: list[FeedItemModel]) -> str:
    """Rebuild a minimal digest for undelivered items (the original text wasn't persisted)."""
    lines = ["Catching up on a few items from your last feed:", ""]
    for it in items:
        reason = f" — {it.reason}" if it.reason else ""
        lines.append(f"- {it.title}{reason}\n  {it.url}")
    return "\n".join(lines)


async def _deliver(chat_id: str, digest: str) -> bool:
    """Send ``digest`` to Telegram. Skips empty/whitespace-only text. Returns whether it sent."""
    if not digest or not digest.strip():
        logger.info("feed_digest_empty_skipped")
        return False
    try:
        await notifier.send_text(chat_id, digest)
        return True
    except Exception as exc:  # delivery failure must not abort the pass
        logger.warning("feed_delivery_failed", error=str(exc))
        return False
