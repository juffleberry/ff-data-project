# The Fantasy League — Record Book

Every result from eleven seasons of a 16-team fantasy football league, 2012–2022,
as a browsable record book.

**→ https://juffleberry.github.io/ff-data-project/**

The league ran on NFL.com as `TheGentlemen'sLeague` (league 1078038). NFL has since
shut the fantasy product down — `fantasy.nfl.com/league/…` now redirects to a news
page — so the game log in `data/` is the surviving copy of that era.

## Layout

```
data/league_h2h.csv    1,206 scraped games, 2012–2022 — the source of truth
data/franchises.csv    season team name -> canonical franchise
build.py               regenerates the site's JSON from those two files
docs/                  the GitHub Pages site (static, no build step)
scrape/                the original 2022 Selenium scraper, kept for provenance
```

## Rebuilding

```bash
python3 build.py
```

Stdlib only — no virtualenv, no install. It writes `docs/data/league_records.json`,
which the page fetches. To preview the site locally:

```bash
python3 -m http.server 8791 --directory docs
```

## What the 2026 rebuild changed

The original transform had three bugs that made the published records wrong:

- **Win % was truncated, not rounded.** It did `str(pct)[0:2] + '%'`, so every
  undefeated matchup rendered as `10%`. 16 of 282 head-to-head entries were wrong.
- **An unfinished season was recorded as played.** The scrape ran on 13 Nov 2022,
  midway through week 10. Weeks 10–16 came back as zeros and `Not yet played`
  placeholders, and five in-progress games were filed as real results — a 0.0–4.8
  Thursday-night snapshot became a loss on the record. 2022 now stops at week 9,
  the last week that finished.
- **Draws were scored as away wins.** The scraped `winner` column fell through to
  the away team on equal scores. Results are now recomputed from the scores.

It also drops the owner-name concordance in favour of `data/franchises.csv`, which
carries the same season-name-to-franchise mapping without anybody's real name, and
adds season-by-season splits, points for/against and best/worst weeks to the output.

## Known gaps

- **2022 weeks 10–16, and all of 2023 and 2024.** Those seasons were played on
  NFL.com and were never scraped. They are almost certainly unrecoverable: league
  pages sat behind a login, so no crawler could reach them, and the Wayback Machine
  and archive.today have **zero** captures of league 1078038 or of the league's
  vanity host. If a leaguemate kept screenshots or ran the scraper themselves,
  that's the only route back.
- **2025 onwards is on Sleeper**, whose public API serves matchups and brackets
  without auth. Folding those seasons in is the obvious next step; nothing in
  `build.py` assumes the NFL-era CSV is the only input.

## History

Built in November 2022 by Shahar Merom (scraper and transform) and Alistair Taylor
(the original React front end, on the `creating-react-app` branch). Rebuilt in 2026
as a static page.
