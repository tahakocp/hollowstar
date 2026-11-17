import json
import unittest

from hollowstar.github import GitHub, GitHubError


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        status, hdrs, payload = self.responses.pop(0)
        return status, hdrs, json.dumps(payload).encode()


class GitHubTest(unittest.TestCase):
    def test_sends_token_and_query(self):
        t = Recorder((200, {}, [1]))
        gh = GitHub("abc", transport=t)
        self.assertEqual(gh.rest("repos/a/b/stargazers/history", per_page=30, page=2), [1])
        method, url, headers, _ = t.calls[0]
        self.assertEqual(method, "GET")
        self.assertIn("per_page=30&page=2", url)
        self.assertEqual(headers["Authorization"], "Bearer abc")

    def test_retries_on_rate_limit(self):
        slept = []
        t = Recorder((403, {"Retry-After": "3"}, {"message": "secondary rate limit"}), (200, {}, {"ok": 1}))
        gh = GitHub("abc", transport=t, sleep=slept.append)
        self.assertEqual(gh.rest("x"), {"ok": 1})
        self.assertEqual(slept, [3.0])

    def test_plain_403_is_not_retried(self):
        t = Recorder((403, {}, {"message": "Resource not accessible"}))
        with self.assertRaises(GitHubError) as ctx:
            GitHub("abc", transport=t, sleep=lambda s: None).rest("x")
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(len(t.calls), 1)

    def test_graphql_errors_raise(self):
        t = Recorder((200, {}, {"errors": [{"message": "Could not resolve"}]}))
        with self.assertRaises(GitHubError):
            GitHub("abc", transport=t).graphql("query{x}")

    def test_graphql_needs_token(self):
        with self.assertRaises(GitHubError):
            GitHub(None, transport=Recorder()).graphql("query{x}")


if __name__ == "__main__":
    unittest.main()
