"""Signals that separate bought stars from earned ones.

Every signal returns a severity between 0 and 1 plus a sentence a human can check.
None of them is proof on its own; the score combines them so that one odd number
(a young author, a docs repo with few forks) does not flag a project by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .history import Shape


@dataclass
class Facts:
    full_name: str
    description: str
    created: date
    pushed: date | None
    stars: int
    forks: int
    watchers: int
    issues: int
    pulls: int
    releases: int
    commits: int | None
    disk_kb: int
    topics: int
    owner_type: str
    owner_created: date | None
    owner_followers: int | None
    owner_repos: int | None
    readme: str = ""
    archived: bool = False
    is_fork: bool = False


@dataclass
class Signal:
    key: str
    weight: float
    severity: float
    detail: str


@dataclass
class Verdict:
    facts: Facts
    shape: Shape | None
    signals: list[Signal] = field(default_factory=list)

    @property
    def score(self) -> int:
        keep = 1.0
        for s in self.signals:
            keep *= 1 - s.weight * s.severity
        return round(100 * (1 - keep))

    @property
    def label(self) -> str:
        if self.facts.stars < MIN_STARS:
            return "too few stars to judge"
        if self.score >= 60:
            return "likely inflated"
        if self.score >= 30:
            return "suspicious"
        return "no strong signal"

    def fired(self) -> list[Signal]:
        return sorted((s for s in self.signals if s.severity > 0), key=lambda s: -s.weight * s.severity)


MIN_STARS = 50

# Wording used by repos that exist to push cracked software or "free" tools.
# Kept narrow on purpose: "desktop" or "pro" alone are far too common.
LURE = re.compile(
    r"\b(crack(ed)?|keygen|activator|activation key|license key|serial key|free download|"
    r"full version|nulled|mod menu|aimbot|wallhack|spoofer|hwid spoof|unlocked premium|"
    r"premium unlocked|pre-?activated)\b",
    re.I,
)
ARCHIVE_PASSWORD = re.compile(r"(password|pass|pwd)\s*[:=]\s*\S+", re.I)
DOWNLOAD_LINK = re.compile(r"https?://\S+\.(zip|rar|7z|exe|msi|scr)\b|releases/download/\S+\.(zip|rar|7z|exe|msi)", re.I)


def ramp(x: float, lo: float, hi: float) -> float:
    """0 at lo, 1 at hi, linear in between. Works for falling ramps too (lo > hi)."""
    if lo == hi:
        return float(x >= hi)
    t = (x - lo) / (hi - lo)
    return max(0.0, min(1.0, t))


def evaluate(f: Facts, sh: Shape | None, today: date) -> Verdict:
    v = Verdict(f, sh)
    add = v.signals.append
    stars = max(f.stars, 1)
    age_days = (today - f.created).days

    if sh and sh.total >= MIN_STARS:
        sev = ramp(sh.burst_days, 6, 2) if sh.days_observed >= 3 else 0.0
        add(Signal("burst", 0.25, sev,
                   f"90% of {sh.total} stars arrived in {sh.burst_days} day(s) starting {sh.burst_start}"))
        if sh.after_rate is not None:
            sev = ramp(sh.after_rate, 0.06, 0.005)
            add(Signal("no_tail", 0.40, sev,
                       f"after the burst, stars/day fell to {sh.after_rate:.1%} of the burst rate "
                       f"({sh.days_after_burst} day(s) observed)"))
        if sh.days_observed >= 21:
            sev = ramp(sh.active_share, 0.25, 0.08)
            add(Signal("silent_days", 0.20, sev,
                       f"stars on {sh.active_share:.0%} of the {sh.days_observed} days since the first star"))

    if f.stars >= MIN_STARS:
        ratio = f.forks / stars
        add(Signal("forks", 0.30, ramp(ratio, 0.02, 0.003),
                   f"{f.forks} forks for {f.stars} stars ({ratio:.2%})"))

        wratio = f.watchers / stars
        add(Signal("watchers", 0.25, ramp(wratio, 0.15, 0.4),
                   f"{f.watchers} watchers for {f.stars} stars ({wratio:.0%}; organic repos sit near 1-3%)"))

        if f.stars >= 200 and f.commits is not None:
            sev = ramp(f.commits, 12, 3) * ramp(f.disk_kb, 500, 50)
            add(Signal("thin", 0.15, sev,
                       f"{f.commits} commit(s), {f.disk_kb} KB on disk, {f.stars} stars"))

        if f.stars >= 300:
            talk = f.issues + f.pulls
            add(Signal("no_conversation", 0.10, 1.0 if talk == 0 else 0.0,
                       f"{f.issues} issues and {f.pulls} pull requests ever opened"))

    if f.owner_created and f.owner_type == "User":
        owner_age = (f.created - f.owner_created).days
        followers = f.owner_followers or 0
        sev = ramp(owner_age, 90, 14) * ramp(followers, 20, 2)
        add(Signal("fresh_owner", 0.20, sev,
                   f"owner account was {owner_age} day(s) old at repo creation, {followers} follower(s)"))

    stuffing = _stuffing(f)
    add(Signal("seo_stuffing", 0.20, stuffing[0], stuffing[1]))

    lure = _lure(f)
    add(Signal("lure", 0.35, lure[0], lure[1]))

    if age_days < 3:
        add(Signal("too_young", 0.0, 1.0, f"repo is {age_days} day(s) old; tail signals not available yet"))
    return v


def _stuffing(f: Facts) -> tuple[float, str]:
    seps = len(re.findall(r"\s[·|•]\s", f.description))
    # Twenty topics is common on honest repos too, so topics alone cap at 0.5.
    sev = max(0.5 * ramp(f.topics, 15, 20), ramp(seps, 2, 5))
    return sev, f"{f.topics} topics, {seps} keyword separators in the description"


def _lure(f: Facts) -> tuple[float, str]:
    # Name and description are short and deliberate, so wording there counts on
    # its own. README wording only counts next to a direct archive/exe link:
    # plenty of honest READMEs say "license key" or "full version".
    hits = sorted({m.group(0).lower() for m in LURE.finditer(f"{f.full_name} {f.description}")})
    links = DOWNLOAD_LINK.search(f.readme) is not None
    readme_hits = sorted({m.group(0).lower() for m in LURE.finditer(f.readme)}) if links else []
    password = links and ARCHIVE_PASSWORD.search(f.readme) is not None
    hits = sorted(set(hits) | set(readme_hits))
    sev = 0.0
    if hits:
        sev = 0.6
    if links and (hits or password):
        sev = 1.0
    parts = []
    if hits:
        parts.append("wording: " + ", ".join(hits[:5]))
    if links:
        parts.append("README links straight to an archive or executable")
    if password:
        parts.append("and gives an archive password")
    return sev, "; ".join(parts) or "no download-lure wording"


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
