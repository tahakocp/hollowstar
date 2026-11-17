from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import __version__
from .check import check
from .github import GitHub, GitHubError, find_token
from .report import (sweep_dict, sweep_markdown, to_json, verdict_dict,
                     verdict_text, verdicts_markdown)
from .sweep import default_query, sweep


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="hollowstar",
        description="Spot inflated GitHub star counts from public, privacy-safe data.",
    )
    p.add_argument("--version", action="version", version=f"hollowstar {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="score one or more repositories")
    c.add_argument("repos", nargs="+", help="owner/repo or https://github.com/owner/repo")
    c.add_argument("--weeks", type=int, default=104, help="star history to read (default 104)")
    c.add_argument("--format", choices=["text", "json", "md"], default="text")
    c.add_argument("--fail-above", type=int, metavar="SCORE",
                   help="exit 2 if any repo scores above SCORE (for CI gates)")

    s = sub.add_parser("sweep", help="scan recent repos for template campaigns")
    s.add_argument("--days", type=int, default=7, help="repos created in the last N days (default 7)")
    s.add_argument("--min-stars", type=int, default=50)
    s.add_argument("--query", help="raw GitHub search query; overrides --days/--min-stars")
    s.add_argument("--limit", type=int, default=300, help="max repos to scan (search caps at 1000)")
    s.add_argument("--format", choices=["text", "json", "md"], default="text")

    args = p.parse_args(argv)
    today = datetime.now(timezone.utc).date()
    gh = GitHub(find_token())
    if not gh.token:
        print("hollowstar: no token found; set GITHUB_TOKEN or run `gh auth login`", file=sys.stderr)
        return 1

    try:
        if args.cmd == "check":
            verdicts = []
            for repo in args.repos:
                try:
                    verdicts.append(check(gh, repo, weeks=args.weeks, today=today))
                except (GitHubError, ValueError) as err:
                    print(f"hollowstar: {repo}: {err}", file=sys.stderr)
            if args.format == "json":
                print(to_json([verdict_dict(v) for v in verdicts]))
            elif args.format == "md":
                print(verdicts_markdown(verdicts))
            else:
                print("\n\n".join(verdict_text(v) for v in verdicts))
            if len(verdicts) < len(args.repos):
                return 1
            if args.fail_above is not None and any(v.score > args.fail_above for v in verdicts):
                return 2
            return 0

        query = args.query or default_query(args.days, args.min_stars, today)
        res = sweep(gh, query, args.limit, today)
        if args.format == "json":
            print(to_json(sweep_dict(res, today)))
        elif args.format == "md":
            print(sweep_markdown(res, today), end="")
        else:
            print(f"scanned {res.scanned} repos for: {query}")
            print(f"{len(res.flagged)} look boosted, {len(res.clusters)} template clusters\n")
            for c in res.clusters[:15]:
                print(f"  {len(c.repos):>3} repos / {len(c.owners):>3} accounts  {c.kind}: {c.key[:50]}")
            print("\ntop clean repos:")
            for r in res.clean[:20]:
                print(f"  {r['stargazers_count']:>6}  {r['full_name']}")
        return 0
    except GitHubError as err:
        print(f"hollowstar: {err}", file=sys.stderr)
        return 1
