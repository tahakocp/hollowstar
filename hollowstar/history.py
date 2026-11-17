"""Daily star counts from GET /repos/{owner}/{repo}/stargazers/history.

Since mid-2026 the stargazer list is limited to a repo's admins, so tools can no
longer look at who starred something. The history endpoint still returns how
many stars arrived each day, which is enough to see the shape of a campaign.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

PER_PAGE = 30  # weeks per page, the endpoint maximum
MAX_PAGES = 100


def fetch_weeks(gh, full_name: str, since: date | None = None, max_pages: int = MAX_PAGES):
    """Return the raw weekly buckets, newest first, stopping once `since` is covered."""
    weeks: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = gh.rest(f"repos/{full_name}/stargazers/history", per_page=PER_PAGE, page=page)
        if not batch:
            break
        weeks.extend(batch)
        oldest = _week_start(batch[-1]["week"])
        if len(batch) < PER_PAGE or (since and oldest <= since):
            break
    return weeks


def _week_start(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def to_daily(weeks: list[dict], start: date | None = None, end: date | None = None) -> list[tuple[date, int]]:
    """Flatten weekly buckets (each starting on Sunday) into sorted (day, stars) pairs."""
    days: dict[date, int] = {}
    for w in weeks:
        first = _week_start(w["week"])
        for i, n in enumerate(w.get("days") or []):
            days[first + timedelta(days=i)] = int(n)
    out = sorted(days.items())
    if start:
        out = [d for d in out if d[0] >= start]
    if end:
        out = [d for d in out if d[0] <= end]
    return out


@dataclass
class Shape:
    total: int
    days_observed: int
    burst_start: date | None
    burst_days: int  # shortest run of days holding 90% of all stars
    burst_stars: int
    days_after_burst: int  # complete days observed after the burst
    after_rate: float | None  # mean stars/day after the burst, divided by mean during it
    active_share: float  # share of observed days with at least one star
    peak_day: int


def shape(daily: list[tuple[date, int]], today: date, share: float = 0.9) -> Shape:
    # Today's bucket is still filling up, so leave it out of rate math.
    daily = [d for d in daily if d[0] < today]
    counts = [n for _, n in daily]
    total = sum(counts)
    if not daily or total == 0:
        return Shape(total, len(daily), None, 0, 0, 0, None, 0.0, 0)

    need = share * total
    best = (0, len(counts))  # (start index, length)
    lo, running = 0, 0
    for hi, n in enumerate(counts):
        running += n
        while running - counts[lo] >= need and lo < hi:
            running -= counts[lo]
            lo += 1
        if running >= need and hi - lo + 1 < best[1]:
            best = (lo, hi - lo + 1)
    start, length = best
    burst = counts[start : start + length]
    after = counts[start + length : start + length + 14]
    after_rate = None
    if len(after) >= 2:
        during = sum(burst) / length
        after_rate = (sum(after) / len(after)) / during if during else None

    first_star = next(i for i, n in enumerate(counts) if n)
    observed = counts[first_star:]
    active = sum(1 for n in observed if n) / len(observed)
    return Shape(
        total=total,
        days_observed=len(observed),
        burst_start=daily[start][0],
        burst_days=length,
        burst_stars=sum(burst),
        days_after_burst=len(after),
        after_rate=after_rate,
        active_share=active,
        peak_day=max(counts),
    )
