"""Pure per-user cooldown helper shared by the manual agent triggers.

A trigger is on cooldown when its last-run timestamp is within ``cooldown_seconds``
of *now*. Returns the integer seconds the caller must wait (rounded up), or ``0``
when the action is allowed. Kept dependency-free so it can be unit-tested without a DB.
"""

import math
from datetime import UTC, datetime


def cooldown_remaining(last_run: datetime | None, cooldown_seconds: int, *, now: datetime | None = None) -> int:
    """Seconds remaining before the action may run again (0 == allowed now).

    ``last_run`` may be timezone-aware (set by the repo as UTC) or naive (as stored
    by SQLite/Postgres ``TIMESTAMP``); naive values are treated as UTC so the two
    paths agree. A non-positive ``cooldown_seconds`` disables the cooldown.
    """
    if last_run is None or cooldown_seconds <= 0:
        return 0
    now = now or datetime.now(UTC)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=UTC)
    elapsed = (now - last_run).total_seconds()
    remaining = cooldown_seconds - elapsed
    return max(0, math.ceil(remaining))
