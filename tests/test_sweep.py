import unittest
from datetime import date

from hollowstar.sweep import desc_key, find_clusters, name_key, quick_flags, star_count_clusters, sweep

TODAY = date(2026, 11, 17)


def repo(owner, name, stars=300, forks=0, desc=None, topics=18, size=12):
    return {
        "full_name": f"{owner}/{name}", "name": name, "owner": {"login": owner},
        "description": desc, "stargazers_count": stars, "forks_count": forks,
        "topics": ["t"] * topics, "size": size, "fork": False,
        "html_url": f"https://github.com/{owner}/{name}", "language": "Python",
    }


def organic(owner, name, stars, forks=None):
    return repo(owner, name, stars, forks if forks is not None else stars // 10,
                desc=f"{name} does a specific job", topics=5, size=4000)


class FakeGH:
    def __init__(self, items):
        self.items = items

    def rest(self, path, **params):
        assert path == "search/repositories"
        start = (params["page"] - 1) * params["per_page"]
        return {"items": self.items[start : start + params["per_page"]]}


class KeysTest(unittest.TestCase):
    def test_name_key_strips_template_suffixes(self):
        self.assertEqual(name_key("IPTV_Player_2.0"), name_key("IPTV-Player"))
        self.assertEqual(name_key("ai--manus2.0"), "aimanus")
        self.assertEqual(name_key("blender-ai-copilot-forge"), "blenderai")

    def test_short_descriptions_are_ignored(self):
        self.assertEqual(desc_key("A tool"), "")
        self.assertTrue(desc_key("A powerful, intuitive IPTV streaming app supporting M3U"))


class ClusterTest(unittest.TestCase):
    def test_same_name_across_accounts(self):
        items = [repo(f"acct{i}", "Gemini-Config-Checker-") for i in range(5)]
        items.append(organic("someone", "gemini-config-checker-v2", 300))
        (c,) = [c for c in find_clusters(items) if c.kind == "name"]
        self.assertEqual(len(c.owners), 6)

    def test_one_account_many_repos_is_not_a_cluster(self):
        items = [repo("same", f"tool-{i}", desc="Same description used across a personal series") for i in range(5)]
        self.assertEqual([c for c in find_clusters(items) if c.kind != "star count"], [])

    def test_star_windows_do_not_chain(self):
        items = [organic(f"o{i}", f"p{i}", 100 + i) for i in range(40)]
        for c in star_count_clusters(items):
            counts = [r["stargazers_count"] for r in c.repos]
            self.assertLessEqual(max(counts) - min(counts), 2)


class QuickFlagsTest(unittest.TestCase):
    def test_hollow(self):
        reasons = quick_flags(repo("x", "y", stars=360, forks=0, topics=20, size=10), TODAY)
        self.assertEqual(len(reasons), 3)

    def test_organic(self):
        self.assertEqual(quick_flags(organic("x", "y", 900), TODAY), [])


class SweepTest(unittest.TestCase):
    def test_campaign_flagged_and_bystanders_kept(self):
        campaign = [repo(f"fresh{i}", "ai--manus", stars=186 + i % 2,
                         desc="AI Manus is a general-purpose AI agent system that supports running tools")
                    for i in range(12)]
        packages = [repo(f"seller{i}", f"{p}-desktop", stars=247 + i % 2)
                    for i, p in enumerate(["office", "kontakt", "serum", "vegas", "cubase", "idea"])]
        bystanders = [organic("a", "git-twig", 186), organic("b", "tinytraffic", 247),
                      organic("c", "shoji-bar", 900)]
        res = sweep(FakeGH(campaign + packages + bystanders), "q", 100, TODAY)
        flagged = set(res.flagged)
        self.assertTrue({r["full_name"] for r in campaign} <= flagged)
        self.assertTrue({r["full_name"] for r in packages} <= flagged)
        self.assertEqual({r["full_name"] for r in res.clean}, {r["full_name"] for r in bystanders})

    def test_popular_idea_with_healthy_repos_is_not_flagged(self):
        items = [organic(f"dev{i}", "todo-app", 150 + 20 * i) for i in range(5)]
        res = sweep(FakeGH(items), "q", 100, TODAY)
        self.assertEqual(res.flagged, {})


if __name__ == "__main__":
    unittest.main()
