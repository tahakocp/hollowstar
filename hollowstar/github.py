"""Minimal GitHub API client (stdlib only).

Token lookup order: GITHUB_TOKEN, GH_TOKEN, then `gh auth token` if the GitHub
CLI is installed. Anonymous access works for star history, but GraphQL and the
search API need a token.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

API = "https://api.github.com"
USER_AGENT = "hollowstar"


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


def find_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var].strip()
    if shutil.which("gh"):
        try:
            out = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return None


# A transport takes (method, url, headers, body) and returns (status, headers, body).
Transport = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read()


class GitHub:
    def __init__(
        self,
        token: str | None = None,
        transport: Transport = urllib_transport,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.token = token
        self.transport = transport
        self.max_retries = max_retries
        self.sleep = sleep
        self.requests = 0

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _request(self, method: str, url: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = self._headers({"Content-Type": "application/json"} if data else None)
        for attempt in range(self.max_retries + 1):
            self.requests += 1
            status, resp_headers, raw = self.transport(method, url, headers, data)
            lower = {k.lower(): v for k, v in resp_headers.items()}
            if status == 202 and attempt < self.max_retries:
                # Stats endpoints answer 202 while GitHub computes the result.
                self.sleep(2 * (attempt + 1))
                continue
            limited = status == 429 or (
                status == 403
                and (lower.get("x-ratelimit-remaining") == "0" or "retry-after" in lower)
            )
            if limited and attempt < self.max_retries:
                self.sleep(_backoff(lower, attempt))
                continue
            if status >= 400:
                try:
                    msg = json.loads(raw).get("message", "")
                except ValueError:
                    msg = raw[:200].decode(errors="replace")
                raise GitHubError(status, msg)
            return json.loads(raw) if raw else None
        raise GitHubError(status, "gave up after retries")

    def rest(self, path: str, **params: Any) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{API}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        return self._request("GET", url)

    def graphql(self, query: str, **variables: Any) -> dict:
        if not self.token:
            raise GitHubError(401, "GraphQL needs a token (set GITHUB_TOKEN or log in with gh)")
        out = self._request("POST", f"{API}/graphql", {"query": query, "variables": variables})
        if out.get("errors"):
            raise GitHubError(200, "; ".join(e.get("message", "") for e in out["errors"]))
        return out["data"]


def _backoff(headers: dict, attempt: int) -> float:
    if "retry-after" in headers:
        try:
            return min(float(headers["retry-after"]), 120.0)
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            return max(1.0, min(float(reset) - time.time() + 1, 120.0))
        except ValueError:
            pass
    return float(2 ** (attempt + 2))
