"""Plain-text, Markdown and JSON output."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from .signals import Verdict
from .sweep import SweepResult


def verdict_dict(v: Verdict) -> dict:
    f = v.facts
    return {
        "repo": f.full_name,
        "score": v.score,
        "label": v.label,
        "stars": f.stars,
        "forks": f.forks,
        "watchers": f.watchers,
        "created": f.created.isoformat(),
        "signals": [
            {"key": s.key, "weight": s.weight, "severity": round(s.severity, 3), "detail": s.detail}
            for s in v.signals
        ],
        "shape": _shape(v),
    }


def _shape(v: Verdict) -> dict | None:
    if not v.shape:
        return None
    d = asdict(v.shape)
    if d["burst_start"]:
        d["burst_start"] = d["burst_start"].isoformat()
    if d["after_rate"] is not None:
        d["after_rate"] = round(d["after_rate"], 4)
    d["active_share"] = round(d["active_share"], 4)
    return d


def verdict_text(v: Verdict) -> str:
    f = v.facts
    lines = [f"{f.full_name}  score {v.score}/100  ({v.label})",
             f"  {f.stars} stars, {f.forks} forks, {f.watchers} watchers, created {f.created}"]
    fired = [s for s in v.fired() if s.weight > 0]
    for s in fired:
        lines.append(f"  - [{s.key}] {s.detail}")
    if not fired:
        lines.append("  - nothing unusual in the public numbers")
    for s in v.signals:
        if s.key == "too_young":
            lines.append(f"  note: {s.detail}")
    return "\n".join(lines)


def verdicts_markdown(vs: list[Verdict]) -> str:
    rows = ["| repo | score | verdict | strongest signals |", "|---|---:|---|---|"]
    for v in vs:
        top = "; ".join(s.detail for s in v.fired()[:2] if s.weight > 0) or "-"
        rows.append(f"| [{v.facts.full_name}](https://github.com/{v.facts.full_name}) | {v.score} | {v.label} | {top} |")
    return "\n".join(rows)


def sweep_dict(res: SweepResult, today: date) -> dict:
    return {
        "generated": today.isoformat(),
        "query": res.query,
        "scanned": res.scanned,
        "flagged": [{"repo": k, "reasons": sorted(set(v))} for k, v in sorted(res.flagged.items())],
        "clusters": [
            {"kind": c.kind, "key": c.key, "accounts": len(c.owners),
             "repos": [r["full_name"] for r in c.repos]}
            for c in res.clusters
        ],
        "clean": [
            {"repo": r["full_name"], "stars": r["stargazers_count"], "forks": r["forks_count"],
             "language": r.get("language"), "description": r.get("description")}
            for r in res.clean
        ],
    }


def sweep_markdown(res: SweepResult, today: date, top: int = 50) -> str:
    out = [f"# New repos worth a look ({today})", "",
           f"Query: `{res.query}`. Scanned {res.scanned} repos, set aside {len(res.flagged)} "
           f"that look boosted, {len(res.clean)} left.", "",
           "| # | repo | stars | forks | language | description |", "|---:|---|---:|---:|---|---|"]
    for i, r in enumerate(res.clean[:top], 1):
        desc = (r.get("description") or "").replace("|", "\\|")[:110]
        out.append(f"| {i} | [{r['full_name']}]({r['html_url']}) | {r['stargazers_count']} | "
                   f"{r['forks_count']} | {r.get('language') or ''} | {desc} |")
    if res.clusters:
        out += ["", "## Template clusters", ""]
        for c in res.clusters[:20]:
            out.append(f"- {len(c.repos)} repos from {len(c.owners)} accounts share a {c.kind} "
                       f"(`{c.key[:40]}`)")
    return "\n".join(out) + "\n"


def to_json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
