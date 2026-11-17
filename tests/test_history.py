import unittest
from datetime import date, timedelta

from hollowstar import history
from tests.helpers import weeks_from_daily


class FakeGH:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def rest(self, path, **params):
        self.calls.append((path, params))
        return self.pages[params["page"] - 1] if params["page"] <= len(self.pages) else []


class ToDailyTest(unittest.TestCase):
    def test_round_trip_keeps_every_day(self):
        start = date(2026, 10, 7)  # a Wednesday, so the first week is partial
        counts = [i % 5 for i in range(30)]
        daily = history.to_daily(weeks_from_daily(start, counts), start=start)
        self.assertEqual([n for _, n in daily][: len(counts)], counts)
        self.assertEqual(daily[0][0], start)

    def test_week_buckets_start_on_sunday(self):
        weeks = [{"week": 1794700800, "total": 3, "days": [1, 2, 0, 0, 0, 0, 0]}]
        daily = history.to_daily(weeks)
        self.assertEqual(daily[0], (date(2026, 11, 15), 1))
        self.assertEqual(daily[0][0].weekday(), 6)


class ShapeTest(unittest.TestCase):
    today = date(2026, 11, 20)

    def series(self, counts):
        start = self.today - timedelta(days=len(counts))
        return [(start + timedelta(days=i), n) for i, n in enumerate(counts)]

    def test_bought_batch_has_short_burst_and_no_tail(self):
        sh = history.shape(self.series([0, 208, 152, 0, 0, 0, 0, 0]), self.today)
        self.assertEqual(sh.total, 360)
        self.assertEqual(sh.burst_days, 2)
        self.assertEqual(sh.after_rate, 0.0)

    def test_launch_spike_with_decay_keeps_a_tail(self):
        counts = [5, 400, 900, 300, 120, 80, 60, 45, 40, 30, 28, 25, 22, 20, 18]
        sh = history.shape(self.series(counts), self.today)
        self.assertGreater(sh.burst_days, 4)
        self.assertGreater(sh.after_rate, 0.05)

    def test_steady_repo_is_active_most_days(self):
        sh = history.shape(self.series([3, 4, 2, 5, 3, 1, 4] * 6), self.today)
        self.assertEqual(sh.active_share, 1.0)
        self.assertGreater(sh.burst_days, 30)

    def test_today_is_ignored(self):
        daily = self.series([0, 100, 0]) + [(self.today, 999)]
        self.assertEqual(history.shape(daily, self.today).total, 100)

    def test_empty(self):
        sh = history.shape([], self.today)
        self.assertEqual(sh.total, 0)
        self.assertIsNone(sh.after_rate)


class FetchWeeksTest(unittest.TestCase):
    def test_stops_when_since_is_covered(self):
        page = [{"week": 1794700800 - i * 604800, "total": 0, "days": [0] * 7} for i in range(30)]
        older = [{"week": page[-1]["week"] - 604800, "total": 0, "days": [0] * 7}]
        gh = FakeGH([page, older])
        weeks = history.fetch_weeks(gh, "a/b", since=date(2026, 10, 1))
        self.assertEqual(len(weeks), 30)
        self.assertEqual(len(gh.calls), 1)
        self.assertEqual(gh.calls[0][0], "repos/a/b/stargazers/history")

    def test_short_page_ends_pagination(self):
        gh = FakeGH([[{"week": 1794700800, "total": 1, "days": [1, 0, 0, 0, 0, 0, 0]}]])
        self.assertEqual(len(history.fetch_weeks(gh, "a/b")), 1)
        self.assertEqual(len(gh.calls), 1)


if __name__ == "__main__":
    unittest.main()
