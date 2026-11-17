"""Find star campaigns across many repos at once.

Fake-star sellers rarely boost one repo. They create dozens of repos from one
template under fresh accounts, push them all into the same star range, and let
them compete in search and Trending. Looking at a single repo misses that; laying
the search results side by side makes the template obvious.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .signals import LURE, ramp

SUFFIXES = re.compile(
    r"([-_.](app|hub|lab|labs|desk|desktop|forge|flow|assets|bridge|suite|studio|addon|"
    r"copilot|mcp|tool|tools|pro|free|202\d|v?\d+(\.\d+)*)|v?\d+\.\d+)+$"
)


def name_key(name: str) -> str:
    n = name.lower().strip("-_.")
    n = SUFFIXES.sub("", n)
    return re.sub(r"[^a-z0-9]", "", n)


def desc_key(desc: str | None) -> str:
    d = re.sub(r"[^a-z0-9]", "", (desc or "").lower())
    return d[:48] if len(d) >= 24 else ""


@dataclass
class Cluster:
    kind: str  # "name" or "description"
    key: str
    repos: list[dict] = field(default_factory=list)

    @property
    def owners(self) -> set[str]:
        return {r["owner"]["login"].lower() for r in self.repos}


@dataclass
class SweepResult:
    query: str
    scanned: int
    clusters: list[Cluster]  # only the clusters that led to a flag
    flagged: dict[str, list[str]]  # full_name -> reasons
    clean: list[dict]


def default_query(days: int, min_stars: int, today: date) -> str:
    since = (today - timedelta(days=days)).isoformat()
    return f"created:>={since} stars:>={min_stars}"


def search(gh, query: str, limit: int) -> list[dict]:
    items: list[dict] = []
    page = 1
    while len(items) < limit and page <= 10:  # search API stops at 1000 results
        out = gh.rest("search/repositories", q=query, sort="stars", order="desc",
                      per_page=min(100, limit - len(items)), page=page)
        batch = out.get("items") or []
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items[:limit]


def find_clusters(items: list[dict], min_owners: int = 3) -> list[Cluster]:
    groups: dict[tuple[str, str], Cluster] = {}
    for r in items:
        for kind, key in (("name", name_key(r["name"])), ("description", desc_key(r.get("description")))):
            if len(key) < 4:
                continue
            groups.setdefault((kind, key), Cluster(kind, key)).repos.append(r)
    clusters = [c for c in groups.values() if len(c.owners) >= min_owners]
    clusters += star_count_clusters(items, min_owners + 1)
    return sorted(clusters, key=lambda c: -len(c.repos))


def star_count_clusters(items: list[dict], min_owners: int = 4, width: int = 2) -> list[Cluster]:
    """Repos from different accounts that landed on (almost) the same star count.

    Sellers deliver packages of N stars, so a batch of repos bought together
    ends up at 247, 247, 248, 247... Windows are capped at `width` stars so a
    dense range of small repos cannot chain into one huge group, and sweep()
    only flags the members that also look hollow.
    """
    ordered = sorted(items, key=lambda r: r["stargazers_count"])
    out, i = [], 0
    while i < len(ordered):
        lo = ordered[i]["stargazers_count"]
        j = i
        while j < len(ordered) and ordered[j]["stargazers_count"] - lo <= width:
            j += 1
        c = Cluster("star count", f"{lo}-{ordered[j - 1]['stargazers_count']}", ordered[i:j])
        if len(c.owners) >= min_owners:
            out.append(c)
            i = j
        else:
            i += 1
    return out


def quick_flags(r: dict, today: date) -> list[str]:
    """Cheap per-repo checks that need nothing beyond a search result."""
    reasons = []
    stars, forks = r["stargazers_count"], r["forks_count"]
    if stars >= 100 and forks / stars < 0.003:
        reasons.append(f"{forks} forks for {stars} stars")
    if len(r.get("topics") or []) >= 15:
        reasons.append(f"{len(r['topics'])} topics")
    desc = r.get("description") or ""
    if len(re.findall(r"\s[·|•]\s", desc)) >= 3:
        reasons.append("keyword-stuffed description")
    lure = LURE.search(f"{r['name']} {desc}")
    if lure:
        reasons.append(f"lure wording: {lure.group(0).lower()}")
    if stars >= 200 and r.get("size", 0) < 50:
        reasons.append(f"{r.get('size', 0)} KB repo with {stars} stars")
    return reasons


def sweep(gh, query: str, limit: int, today: date, min_owners: int = 3) -> SweepResult:
    items = [r for r in search(gh, query, limit) if not r.get("fork")]
    clusters = find_clusters(items, min_owners)
    flagged: dict[str, list[str]] = defaultdict(list)
    used: list[Cluster] = []
    for c in clusters:
        hollow = [r for r in c.repos if quick_flags(r, today)]
        if c.kind == "star count":
            # Equal counts alone prove nothing; only hollow members are named.
            if len(hollow) < max(min_owners + 1, len(c.repos) // 2):
                continue
            members = hollow
        elif c.kind == "description":
            # Distinct accounts publishing the same description is the template itself.
            members = c.repos
        else:
            # A shared name is normal for a popular idea ("todo-app"); require the
            # group to look hollow before treating it as a campaign.
            if len(hollow) < max(2, len(c.repos) // 2):
                continue
            members = c.repos
        used.append(c)
        for r in members:
            flagged[r["full_name"]].append(
                f"one of {len(c.repos)} repos from {len(c.owners)} accounts sharing a {c.kind} pattern"
            )
    for r in items:
        reasons = quick_flags(r, today)
        if len(reasons) >= 2 or r["full_name"] in flagged:
            flagged[r["full_name"]].extend(reasons)
    clean = [r for r in items if r["full_name"] not in flagged]
    return SweepResult(query, len(items), used, dict(flagged), clean)


def score_hint(r: dict) -> float:
    """Severity of the fork ratio alone, used to order the clean list in reports."""
    stars = max(r["stargazers_count"], 1)
    return ramp(r["forks_count"] / stars, 0.02, 0.003)
