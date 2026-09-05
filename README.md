# The Fantasy League — Record Book

Fourteen seasons of a 16-team fantasy football league, 2012–2026, rebuilt from
every source that survived NFL.com shutting its fantasy platform down.

**→ https://juffleberry.github.io/ff-data-project/**

## Why this repo exists

The league ran on NFL.com as `TheGentlemen'sLeague` (league 1078038) from 2012 to
2024, then moved to Sleeper. NFL has since retired the fantasy website —
`fantasy.nfl.com/league/…` redirects to a news page, and neither the Wayback
Machine nor archive.today has a single capture of the league, because the pages
were behind a login that crawlers could never reach.

What survived, and what this repo preserves:

| Source | Covers | Gives us |
| --- | --- | --- |
| `data/league_h2h.csv` | 2012 – 2022 wk9 | Individual game scores, scraped in Nov 2022 |
| `data/nfl-api/` | 2012 – 2024 | Final season standings, straight from NFL's API |
| `data/sleeper/` | 2025 – 2026 | Matchups, rosters, transactions, drafts |

NFL's **API outlived its website**. `api.fantasy.nfl.com/v2/league/standings` is
still public and unauthenticated, and still returns every season back to 2012 —
which is how the 2022–2024 records were recovered after the site went away. Those
responses are archived here verbatim; if the API follows the website, this repo is
the record.

## Layout

```
build.py               regenerates docs/data/league_records.json from everything below
data/league_h2h.csv    1,206 scraped games, 2012-2022
data/nfl-api/          14 raw standings responses, one per season
data/sleeper/          league, rosters, matchups, transactions, drafts, brackets
data/franchises.csv    season team name -> franchise (see "Franchise identity")
data/sleeper_aliases.csv  Sleeper roster id -> franchise
docs/                  the GitHub Pages site — static, no build step
```

## Rebuilding

```bash
python3 build.py
```

Stdlib only, no install. Preview the site with:

```bash
python3 -m http.server 8791 --directory docs
```

## Franchise identity

Team names change nearly every season, so they can't identify anyone. Neither can
the team slot: slot 5 has had three different managers, and slot 4 changed hands
after 2022. A franchise here is **one manager's continuous run in one slot**,
derived from the API's `ownerUserId`, with two documented exceptions where a
manager changed NFL accounts (see `SAME_MANAGER` in `build.py`).

No real names are published. `data/franchises.csv` carries the season-name to
franchise mapping, and the archived API responses contain only numeric user ids.
Sleeper's `users` endpoint is deliberately not archived here: its display names are
people's handles. Rosters are joined to franchises through `data/sleeper_aliases.csv`
by roster id instead.

## One redaction

A 2019 team name has been replaced with `[name redacted]` in every file, including
the archived API response. It is the only deliberate departure from what the
sources returned, and it is noted here so the archive can still be trusted.

## What the rebuild fixed

The original 2022 transform produced records that were wrong in three ways:

- **Win % was truncated, not rounded** — `str(pct)[0:2] + '%'`, so every undefeated
  matchup rendered as `10%`. 16 of 282 head-to-head entries were affected.
- **An unfinished season was recorded as played.** The scrape ran mid-week-10 in
  2022; five in-progress games were filed as final results.
- **Draws were scored as away wins** — the scraped `winner` column fell through to
  the away team on equal scores. Results are now recomputed from the scores.

## Known gaps

- **Matchup-level data is missing for 2022 wk10 – 2024.** Season records for those
  years are recovered and complete, but the individual games are gone: they only
  ever existed on the retired website.
- **Rosters, transactions and draft results for the NFL years are unavailable.**
  Those API endpoints require an authorized app key; only `standings` and `teams`
  are open. Sleeper has all of it from 2025 on.
- **2026 is in progress** and carries no results yet.

## History

Built in November 2022 by Shahar Merom (scraper, transform) and Alistair Taylor
(the original React front end, still on the `creating-react-app` branch).
Rebuilt and extended in 2026.
