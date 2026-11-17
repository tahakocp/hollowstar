"""Collect the public facts about one repository and score them."""

from __future__ import annotations

import base64
import re
from datetime import date, datetime, timedelta, timezone

from . import history
from .github import GitHub, GitHubError
from .signals import Facts, Verdict, evaluate, parse_day

QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner description createdAt pushedAt isFork isArchived diskUsage
    stargazerCount forkCount
    watchers { totalCount }
    issues { totalCount }
    pullRequests { totalCount }
    releases { totalCount }
    repositoryTopics(first: 1) { totalCount }
    defaultBranchRef { target { ... on Commit { history(first: 0) { totalCount } } } }
    owner {
      __typename login
      ... on User { createdAt followers { totalCount } repositories(privacy: PUBLIC) { totalCount } }
      ... on Organization { createdAt }
    }
  }
}
"""

REPO_RE = re.compile(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def parse_repo(arg: str) -> tuple[str, str]:
    m = REPO_RE.match(arg.strip())
    if not m:
        raise ValueError(f"expected owner/repo or a github.com URL, got {arg!r}")
    return m.group(1), m.group(2)


def facts_from_graphql(repo: dict, readme: str = "") -> Facts:
    owner = repo["owner"]
    branch = repo.get("defaultBranchRef") or {}
    commits = ((branch.get("target") or {}).get("history") or {}).get("totalCount")
    return Facts(
        full_name=repo["nameWithOwner"],
        description=repo.get("description") or "",
        created=parse_day(repo["createdAt"]),
        pushed=parse_day(repo.get("pushedAt")),
        stars=repo["stargazerCount"],
        forks=repo["forkCount"],
        watchers=repo["watchers"]["totalCount"],
        issues=repo["issues"]["totalCount"],
        pulls=repo["pullRequests"]["totalCount"],
        releases=repo["releases"]["totalCount"],
        commits=commits,
        disk_kb=repo.get("diskUsage") or 0,
        topics=repo["repositoryTopics"]["totalCount"],
        owner_type=owner["__typename"],
        owner_created=parse_day(owner.get("createdAt")),
        owner_followers=(owner.get("followers") or {}).get("totalCount"),
        owner_repos=(owner.get("repositories") or {}).get("totalCount"),
        readme=readme,
        archived=repo.get("isArchived", False),
        is_fork=repo.get("isFork", False),
    )


def fetch_readme(gh: GitHub, full_name: str) -> str:
    try:
        data = gh.rest(f"repos/{full_name}/readme")
    except GitHubError as err:
        if err.status == 404:
            return ""
        raise
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")[:200_000]
    return ""


def check(gh: GitHub, repo_arg: str, weeks: int = 104, today: date | None = None) -> Verdict:
    today = today or datetime.now(timezone.utc).date()
    owner, name = parse_repo(repo_arg)
    data = gh.graphql(QUERY, owner=owner, name=name)
    repo = data.get("repository")
    if repo is None:
        raise GitHubError(404, f"{owner}/{name} not found")
    full = repo["nameWithOwner"]
    readme = fetch_readme(gh, full)
    f = facts_from_graphql(repo, readme)
    since = max(f.created, today - timedelta(weeks=weeks))
    pages = max(1, min(history.MAX_PAGES, weeks // history.PER_PAGE + 1))
    weeks_raw = history.fetch_weeks(gh, full, since=since, max_pages=pages)
    daily = history.to_daily(weeks_raw, start=since, end=today)
    return evaluate(f, history.shape(daily, today), today)
