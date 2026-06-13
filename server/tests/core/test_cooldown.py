from datetime import UTC, datetime, timedelta

from src.core.cooldown import cooldown_remaining


def test_no_last_run_is_allowed() -> None:
    assert cooldown_remaining(None, 300) == 0


def test_within_window_is_blocked_with_remaining_seconds() -> None:
    now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=100)
    # 300s window, 100s elapsed -> 200s remaining.
    assert cooldown_remaining(last, 300, now=now) == 200


def test_after_window_is_allowed() -> None:
    now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=301)
    assert cooldown_remaining(last, 300, now=now) == 0


def test_naive_timestamp_is_treated_as_utc() -> None:
    # SQLite/Postgres TIMESTAMP columns read back naive; must not crash or mis-compare.
    now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    last_naive = (now - timedelta(seconds=60)).replace(tzinfo=None)
    assert cooldown_remaining(last_naive, 300, now=now) == 240


def test_zero_cooldown_disables_gate() -> None:
    now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    assert cooldown_remaining(now, 0, now=now) == 0
