from datetime import date, datetime, timedelta, timezone

from hollowstar.signals import Facts


def week_ts(d: date) -> int:
    """Unix timestamp of the Sunday that starts d's week, as the API returns it."""
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)
    return int(datetime(sunday.year, sunday.month, sunday.day, tzinfo=timezone.utc).timestamp())


def weeks_from_daily(start: date, counts: list[int]) -> list[dict]:
    """Build API-shaped weekly buckets (newest first) from a list of daily counts."""
    buckets: dict[int, list[int]] = {}
    for i, n in enumerate(counts):
        d = start + timedelta(days=i)
        ts = week_ts(d)
        days = buckets.setdefault(ts, [0] * 7)
        days[(d.weekday() + 1) % 7] += n
    return [{"week": ts, "total": sum(v), "days": v} for ts, v in sorted(buckets.items(), reverse=True)]


def facts(**kw) -> Facts:
    base = dict(
        full_name="someone/project",
        description="A small tool that does one thing well",
        created=date(2026, 9, 1),
        pushed=date(2026, 11, 1),
        stars=1200,
        forks=110,
        watchers=18,
        issues=40,
        pulls=25,
        releases=6,
        commits=340,
        disk_kb=2400,
        topics=6,
        owner_type="User",
        owner_created=date(2017, 3, 2),
        owner_followers=150,
        owner_repos=40,
    )
    base.update(kw)
    return Facts(**base)
