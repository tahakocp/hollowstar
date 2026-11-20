# hollowstar

**Tells you whether a GitHub repo's stars were earned or bought, using only data GitHub still makes public.**

![hollowstar checking sveltejs/svelte, then sweeping the past week of new repos](docs/demo.gif)

<sub>Real run, 2026-11-20 (cast file: [docs/demo.cast](docs/demo.cast)). The sweep counts are for that day.</sub>

What a flagged repo looks like:

```
$ hollowstar check some-account/daw-plugin-desktop
some-account/daw-plugin-desktop  score 77/100  (likely inflated)
  360 stars, 0 forks, 0 watchers, created 2026-11-13
  - [no_tail] after the burst, stars/day fell to 0.0% of the burst rate (2 day(s) observed)
  - [forks] 0 forks for 360 stars (0.00%)
  - [burst] 90% of 360 stars arrived in 2 day(s) starting 2026-11-13
  - [fresh_owner] owner account was 32 day(s) old at repo creation, 0 follower(s)
  - [no_conversation] 0 issues and 0 pull requests ever opened
  - [seo_stuffing] 17 topics, 0 keyword separators in the description
```

(The repo is real; the account name is replaced here.)

## Why this exists

Fake-star detectors used to work by listing a repo's stargazers and checking each account. In July 2026 GitHub limited the stargazer list to a repo's own admins, so those tools now get a 404 or an empty list. The stars are still being sold.

What's still public is enough if you look at the *shape* instead of the people:

- **Star history.** `GET /repos/{owner}/{repo}/stargazers/history` returns daily counts with no identities. A bought package lands in one or two days and then stops dead. A launch on Hacker News also spikes, but it keeps a tail for weeks.
- **Ratios that are expensive to fake.** People who star a real tool also fork it, open issues, and send PRs. Sellers usually deliver stars only; when they deliver watchers too, they overdo it (one repo had 387 watchers for 509 stars).
- **The campaign around the repo.** Sellers don't boost one repo. They push a template to dozens of fresh accounts and buy the same package for each, so you see 22 unrelated "desktop" apps from 22 accounts all sitting at 247-249 stars.

## Install

Python 3.10+, no dependencies.

```bash
pip install git+https://github.com/TahaKocpinar/hollowstar
```

It needs a GitHub token for GraphQL and search. If you're logged in with the `gh` CLI it picks that up; otherwise set `GITHUB_TOKEN`. Any token works, no scopes needed.

## Usage

```bash
hollowstar check owner/repo [owner/repo ...]          # score repos
hollowstar check https://github.com/owner/repo --format json
hollowstar check owner/repo --fail-above 60            # exit 2 above the threshold, for CI

hollowstar sweep                                       # repos created in the last 7 days, 50+ stars
hollowstar sweep --days 30 --min-stars 200 --format md
hollowstar sweep --query "topic:mcp created:>=2026-11-01" --format json
```

`check` costs 3-4 API calls per repo. `sweep` reads up to 1,000 search results (10 calls) and works from those alone.

### What `check` looks at

| signal | what it measures | weight |
|---|---|---:|
| `no_tail` | stars/day after the burst vs during it | 0.40 |
| `lure` | crack/keygen/"free download" wording, README linking straight to a `.zip`/`.exe` with a password | 0.35 |
| `forks` | forks per star (below ~0.3% is rare for real code) | 0.30 |
| `burst` | fewest days holding 90% of the stars | 0.25 |
| `watchers` | watchers per star (organic repos sit near 1-3%) | 0.25 |
| `silent_days` | share of days with any star at all, once the repo is 3+ weeks old | 0.20 |
| `fresh_owner` | owner account age at repo creation, and followers | 0.20 |
| `seo_stuffing` | `a · b · c · d` keyword descriptions; 15-20 topics count for half | 0.20 |
| `thin` | very few commits and almost nothing on disk, with 200+ stars | 0.15 |
| `no_conversation` | 300+ stars and not a single issue or PR, ever | 0.10 |

Each signal has a severity from 0 to 1, and the score is `100 × (1 − Π(1 − weight × severity))`. One odd number doesn't flag a repo: a viral launch with a real fork ratio scores under 30, and so does a new author's first hit. Scores of 30+ say *suspicious*, 60+ *likely inflated*. Repos under 50 stars aren't judged.

### What `sweep` looks at

It groups search results three ways and only flags a group when its members also look hollow:

- the same description published by different accounts,
- the same name once suffixes like `-desktop`, `-hub`, `2.0` are stripped,
- star counts within 2 of each other across 5+ accounts (only the hollow members are named).

The rest of the results come out as a clean list, which is the point: a "new this week" feed where the first page isn't 30 copies of the same lure.

## Measured on 17 November 2026

`hollowstar sweep --days 7 --min-stars 100 --limit 400`, i.e. every repo created 10-17 November with 100+ stars that search returns:

- **274 of 400 repos (68%) were set aside** as campaign members. The largest template was one description published by 110 accounts across 154 repos. Others: an IPTV player from 36 accounts, a "config checker" from 21 accounts all at 473-475 stars, and 22 "desktop" builds of commercial software (office suites, DAWs, IDEs) from 22 accounts at 247-249 stars.

To see whether `check` agrees with `sweep`, I ran it on samples from each side. The two use mostly different evidence (`check` reads the star history and the owner account; `sweep` never does):

| sample | likely inflated | suspicious | no strong signal |
|---|---:|---:|---:|
| 50 random repos `sweep` set aside | 45 | 5 | 0 |
| 50 most-starred repos `sweep` kept | 2 | 2 | 46 |
| 35 most-starred repos of the past 6 months to 3 years | 0 | 0 | 35 |

The 2 + 2 in the middle row are worth a look by hand; `sweep` doesn't catch boosted repos that don't belong to a visible template. There is no public ground truth for fake stars, so read this as agreement between two independent methods, not as accuracy.

## Use it in CI

Curated lists get a steady stream of PRs adding boosted repos. The action scores whatever you pass it and fails above a threshold:

```yaml
- uses: TahaKocpinar/hollowstar@v0.1.0
  with:
    repos: owner/one owner/two
    fail-above: "60"
```

[`examples/awesome-list-gate.yml`](examples/awesome-list-gate.yml) pulls the repo links out of a README diff and checks them. [`examples/weekly-feed.yml`](examples/weekly-feed.yml) publishes a weekly clean list.

## Limits

- It reads public numbers, so it can be wrong in both directions. A seller who also buys forks and spreads delivery over weeks will get through; a real repo that only gets starred from one newsletter mention can look bursty. The output always shows the evidence so a person can decide.
- Campaigns that use different names and descriptions per repo and real-looking fork counts only show up in `check`, not in `sweep`.
- GitHub search returns at most 1,000 results per query. Narrow the query (`--days`, `--min-stars`, `topic:`) for bigger sweeps.
- Star history is read for the last 104 weeks by default (`--weeks`).

## Türkçe

**hollowstar**, bir GitHub reposunun yıldızlarının gerçek mi yoksa satın alınmış mı olduğunu, GitHub'ın hâlâ herkese açık tuttuğu verilerle tahmin eder.

GitHub, Temmuz 2026'da yıldız verenlerin listesini yalnızca repo yöneticilerine açtı. Hesap hesap kontrol eden eski sahte yıldız araçları bu yüzden artık çalışmıyor. hollowstar kişilere bakmıyor. Yıldızların günlere dağılımına (satın alınan paket bir-iki günde gelir ve kesilir), fork/izleyici/issue oranlarına ve aynı şablonla açılmış repo kümelerine bakıyor.

```bash
pip install git+https://github.com/TahaKocpinar/hollowstar
hollowstar check sahip/repo        # tek repo puanı (0-100)
hollowstar sweep --days 7          # son 7 günün yeni repolarında kampanya taraması
```

17 Kasım 2026'da 100'den fazla yıldızı olan ve son bir haftada açılan 400 reponun 274'ü (%68) kampanya kümesi olarak ayrıldı. Puanlar kanıt değil, inceleme için bir işarettir; çıktı her zaman gerekçesini gösterir.

## License

MIT
