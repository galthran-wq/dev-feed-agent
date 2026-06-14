"""APScheduler job that curates a feed for every eligible user on an interval.

Errors are always contained: a failure for one user never aborts the others, and the
scheduled job itself never raises (which would otherwise drop the job)."""

from typing import Any

import structlog
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.connections import ConnectionRepository
from src.services import feed
from src.services.channels import TelegramChannel

logger = structlog.get_logger()

_scheduler: Any | None = None


async def poll_all_users() -> None:
    if not settings.agent_enabled:
        logger.info("poll_skipped_agent_disabled")
        return
    try:
        async with AsyncSessionLocal() as session:
            conns = await ConnectionRepository(session).list_feedable()
        logger.info("poll_cycle_start", users=len(conns))
        for conn in conns:
            try:
                # Fresh session per user so one rollback can't poison the others.
                async with AsyncSessionLocal() as session:
                    bound = await ConnectionRepository(session).get_by_user_id(conn.user_id)
                    if bound is not None and bound.telegram_chat_id:
                        channel = TelegramChannel(bound.telegram_chat_id)
                        await feed.run_for_user(session, bound, channel=channel)
            except Exception as exc:
                logger.error("poll_user_failed", user_id=str(conn.user_id), error=str(exc))
    except Exception as exc:  # the scheduler must survive no matter what
        logger.error("poll_cycle_failed", error=str(exc))


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        poll_all_users,
        trigger="interval",
        minutes=settings.poll_interval_minutes,
        id="poll_all_users",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("scheduler_started", interval_minutes=settings.poll_interval_minutes)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler_stopped")
