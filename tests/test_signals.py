import unittest
from datetime import date, timedelta

from hollowstar.history import shape
from hollowstar.signals import evaluate, ramp
from tests.helpers import facts

TODAY = date(2026, 11, 17)


def series(counts, end=TODAY):
    start = end - timedelta(days=len(counts))
    return [(start + timedelta(days=i), n) for i, n in enumerate(counts)]


def by_key(v):
    return {s.key: s for s in v.signals}


class RampTest(unittest.TestCase):
    def test_rising_and_falling(self):
        self.assertEqual(ramp(5, 0, 10), 0.5)
        self.assertEqual(ramp(-1, 0, 10), 0.0)
        self.assertEqual(ramp(2, 6, 2), 1.0)
        self.assertEqual(ramp(8, 6, 2), 0.0)


class EvaluateTest(unittest.TestCase):
    def test_organic_repo_scores_low(self):
        counts = [8, 12, 9, 15, 30, 22, 11, 9, 7, 10, 13, 9, 8, 6] * 6
        f = facts(stars=sum(counts))
        v = evaluate(f, shape(series(counts), TODAY), TODAY)
        self.assertLess(v.score, 15, [s.detail for s in v.fired()])
        self.assertEqual(v.label, "no strong signal")

    def test_template_repo_scores_high(self):
        counts = [0, 0, 208, 152, 0, 0, 0]
        f = facts(
            full_name="ben-x-42/some-daw-desktop",
            created=TODAY - timedelta(days=5),
            stars=360, forks=0, watchers=0, issues=0, pulls=0, commits=3, disk_kb=40,
            topics=18, owner_created=TODAY - timedelta(days=37), owner_followers=0,
        )
        v = evaluate(f, shape(series(counts), TODAY), TODAY)
        keys = {s.key for s in v.fired()}
        self.assertGreaterEqual(v.score, 60)
        self.assertEqual(v.label, "likely inflated")
        self.assertTrue({"burst", "no_tail", "forks", "fresh_owner", "no_conversation"} <= keys)

    def test_viral_launch_alone_is_not_flagged(self):
        counts = [5, 400, 900, 300, 120, 80, 60, 45, 40, 30, 28, 25, 22, 20, 18]
        f = facts(created=TODAY - timedelta(days=16), stars=sum(counts), forks=160, watchers=30)
        v = evaluate(f, shape(series(counts), TODAY), TODAY)
        self.assertLess(v.score, 30)

    def test_botted_watchers(self):
        f = facts(stars=509, forks=13, watchers=387)
        self.assertEqual(by_key(evaluate(f, None, TODAY))["watchers"].severity, 1.0)

    def test_small_repo_is_not_judged(self):
        f = facts(stars=20, forks=0, watchers=0)
        v = evaluate(f, None, TODAY)
        self.assertEqual(v.label, "too few stars to judge")
        self.assertNotIn("forks", by_key(v))

    def test_organisations_skip_owner_age(self):
        f = facts(owner_type="Organization", owner_created=TODAY, owner_followers=None)
        self.assertNotIn("fresh_owner", by_key(evaluate(f, None, TODAY)))

    def test_description_keyword_stuffing(self):
        f = facts(description="Blender AI copilot · blender · blender 3d · blender addon · blender plugin · blender scripting")
        self.assertEqual(by_key(evaluate(f, None, TODAY))["seo_stuffing"].severity, 1.0)

    def test_twenty_topics_alone_is_mild(self):
        f = facts(topics=20)
        self.assertEqual(by_key(evaluate(f, None, TODAY))["seo_stuffing"].severity, 0.5)

    def test_lure_in_description(self):
        f = facts(description="Photo editor full version with keygen")
        s = by_key(evaluate(f, None, TODAY))["lure"]
        self.assertEqual(s.severity, 0.6)
        self.assertIn("keygen", s.detail)

    def test_readme_lure_needs_a_download_link(self):
        honest = facts(readme="Enter your license key in Settings to unlock the full version.")
        self.assertEqual(by_key(evaluate(honest, None, TODAY))["lure"].severity, 0.0)
        lure = facts(readme="Get the full version: https://example.net/setup.zip  Password: 2026")
        self.assertEqual(by_key(evaluate(lure, None, TODAY))["lure"].severity, 1.0)

    def test_young_repo_gets_a_note(self):
        f = facts(created=TODAY - timedelta(days=1))
        note = by_key(evaluate(f, None, TODAY))["too_young"]
        self.assertEqual(note.weight, 0.0)


if __name__ == "__main__":
    unittest.main()
