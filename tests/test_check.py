import base64
import io
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest import mock

from hollowstar import cli
from hollowstar.check import check, parse_repo
from tests.helpers import weeks_from_daily

TODAY = date(2026, 11, 17)


def repo_node(**kw):
    node = {
        "nameWithOwner": "fresh-acct/daw-suite-desktop", "description": "DAW suite desktop setup",
        "createdAt": "2026-11-12T23:36:24Z", "pushedAt": "2026-11-16T09:56:47Z",
        "isFork": False, "isArchived": False, "diskUsage": 30, "stargazerCount": 360,
        "forkCount": 0, "watchers": {"totalCount": 0}, "issues": {"totalCount": 0},
        "pullRequests": {"totalCount": 0}, "releases": {"totalCount": 1},
        "repositoryTopics": {"totalCount": 17},
        "defaultBranchRef": {"target": {"history": {"totalCount": 3}}},
        "owner": {"__typename": "User", "login": "fresh-acct", "createdAt": "2026-10-12T10:00:00Z",
                  "followers": {"totalCount": 0}, "repositories": {"totalCount": 1}},
    }
    node.update(kw)
    return node


class FakeGH:
    token = "t"

    def __init__(self, node, daily_start, counts, readme=""):
        self.node, self.weeks = node, weeks_from_daily(daily_start, counts)
        self.readme = readme

    def graphql(self, query, **v):
        return {"repository": self.node}

    def rest(self, path, **params):
        if path.endswith("/readme"):
            return {"encoding": "base64", "content": base64.b64encode(self.readme.encode()).decode()}
        return self.weeks if params.get("page", 1) == 1 else []


class ParseRepoTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(parse_repo("a/b"), ("a", "b"))
        self.assertEqual(parse_repo("https://github.com/a/b.git"), ("a", "b"))
        self.assertEqual(parse_repo("https://github.com/a-1/b.c/"), ("a-1", "b.c"))
        with self.assertRaises(ValueError):
            parse_repo("just-a-name")


class CheckTest(unittest.TestCase):
    def test_end_to_end_on_a_bought_batch(self):
        gh = FakeGH(repo_node(), date(2026, 11, 12), [0, 208, 152, 0, 0, 0],
                    readme="Download: https://example.net/files/setup.rar password: 1234")
        v = check(gh, "fresh-acct/daw-suite-desktop", today=TODAY)
        self.assertGreaterEqual(v.score, 80)
        self.assertEqual(v.shape.burst_days, 2)

    def test_cli_fail_above(self):
        gh = FakeGH(repo_node(), date(2026, 11, 12), [0, 208, 152, 0, 0, 0])
        with mock.patch.object(cli, "GitHub", return_value=gh), \
             mock.patch.object(cli, "find_token", return_value="t"):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["check", "fresh-acct/daw-suite-desktop", "--fail-above", "50"])
        self.assertEqual(code, 2)
        self.assertIn("likely inflated", out.getvalue())

    def test_cli_json(self):
        start = TODAY - timedelta(days=84)
        counts = [8, 12, 9, 15, 30, 22, 11] * 12
        node = repo_node(nameWithOwner="lab/steady", createdAt=f"{start}T00:00:00Z",
                         stargazerCount=sum(counts), forkCount=120, watchers={"totalCount": 20},
                         issues={"totalCount": 33}, diskUsage=5000, repositoryTopics={"totalCount": 4},
                         defaultBranchRef={"target": {"history": {"totalCount": 410}}},
                         owner={"__typename": "Organization", "login": "lab", "createdAt": "2015-01-01T00:00:00Z"})
        gh = FakeGH(node, start, counts)
        with mock.patch.object(cli, "GitHub", return_value=gh), \
             mock.patch.object(cli, "find_token", return_value="t"):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["check", "lab/steady", "--format", "json", "--fail-above", "50"])
        self.assertEqual(code, 0)
        self.assertIn('"label": "no strong signal"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
