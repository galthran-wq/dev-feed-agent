"""APScheduler job that polls GitHub for every eligible user on an interval.

Errors are always contained: a failure for one user never aborts the others, and
the scheduled job itself never raises (which would otherwise kill the job)."""

from typing import Any

import structlog
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.repositories.github_profiles import GithubProfileRepository
from src.services import discovery_service

logger = structlog.get_logger()

_scheduler: Any | None = None


async def poll_all_users() -> None:
    if not settings.agent_enabled:
        logger.info("poll_skipped_agent_disabled")
        return
    try:
        async with AsyncSessionLocal() as session:
            profiles = await GithubProfileRepository(session).list_pollable()
        logger.info("poll_cycle_start", users=len(profiles))
        for profile in profiles:
            try:
                # Fresh session per user so one rollback can't poison the others.
                async with AsyncSessionLocal() as session:
                    bound = await GithubProfileRepository(session).get_by_user_id(profile.user_id)
                    if bound is not None:
                        await discovery_service.run_for_user(session, bound)
            except Exception as exc:
                logger.error("poll_user_failed", user_id=str(profile.user_id), error=str(exc))
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
