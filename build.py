#!/usr/bin/env python3
"""Turn the scraped game log into the JSON the site reads.

    python3 build.py

Reads  data/league_h2h.csv      one row per game, 2012-2022
       data/franchises.csv      season team name -> canonical franchise
Writes docs/data/league_records.json

Stdlib only, so it runs anywhere with a python3 and no install step.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data"
OUT = ROOT / "docs" / "data"

# The 2012-2022 scrape ran on 13 Nov 2022, midway through week 10. Weeks 10-16
# came back as zeros and "Not yet played" placeholders, and the original
# transform recorded them as real results — a 0.0-4.8 in-progress game became a
# loss on the record. Week 9 is the last week that finished.
INCOMPLETE = {("2022", str(w)) for w in range(10, 17)}
PLACEHOLDER = "Not yet played"


def load_games():
    """Yield (year, round, franchise_a, score_a, franchise_b, score_b)."""
    alias = {}
    with open(RAW / "franchises.csv", newline="") as f:
        for row in csv.DictReader(f):
            alias[(row["year"], row["team_name"])] = row["franchise"]

    with open(RAW / "league_h2h.csv", newline="") as f:
        for row in csv.DictReader(f):
            year, rnd = row["year"], row["round"]
            if (year, rnd) in INCOMPLETE:
                continue
            home, away = row["home_team"], row["away_team"]
            if PLACEHOLDER in (home, away):
                continue
            yield (
                year,
                rnd,
                alias[(year, home)],
                float(row["home_score"]),
                alias[(year, away)],
                float(row["away_score"]),
            )


def blank():
    return {"wins": 0, "losses": 0, "draws": 0, "pointsFor": 0.0, "pointsAgainst": 0.0}


def record(t):
    """Add derived W-L-D / win% / points fields to an accumulator."""
    games = t["wins"] + t["losses"] + t["draws"]
    t = dict(t, gamesPlayed=games)
    t["record"] = f"{t['wins']}-{t['losses']}-{t['draws']}"
    # The original wrote str(pct)[0:2] + '%', which truncated rather than
    # rounded — every undefeated matchup rendered as "10%".
    t["winPercentage"] = round((t["wins"] + t["draws"] * 0.5) / games * 100, 1) if games else 0.0
    for k in ("pointsFor", "pointsAgainst"):
        t[k] = round(t[k], 2)
    t["avgPointsFor"] = round(t["pointsFor"] / games, 2) if games else 0.0
    t["avgPointsAgainst"] = round(t["pointsAgainst"] / games, 2) if games else 0.0
    return t


def main():
    overall = defaultdict(blank)
    versus = defaultdict(lambda: defaultdict(blank))
    by_season = defaultdict(lambda: defaultdict(blank))
    weeks = defaultdict(list)
    seasons = set()

    for year, rnd, a, sa, b, sb in load_games():
        seasons.add(year)
        for me, mine, them, theirs in ((a, sa, b, sb), (b, sb, a, sa)):
            # Recompute the result from the scores. The scraped `winner` column
            # picked the away team whenever scores were equal, so every draw in
            # the file was filed as an away win.
            outcome = "wins" if mine > theirs else "losses" if mine < theirs else "draws"
            for acc in (overall[me], versus[me][them], by_season[me][year]):
                acc[outcome] += 1
                acc["pointsFor"] += mine
                acc["pointsAgainst"] += theirs
            weeks[me].append({"points": round(mine, 2), "year": year, "round": int(rnd), "opponent": them})

    out = {}
    for team in sorted(overall):
        played = sorted(by_season[team])
        games = sorted(weeks[team], key=lambda w: w["points"])
        out[team] = {
            "franchise": team,
            "allTime": dict(
                record(overall[team]),
                seasons=len(played),
                firstSeason=played[0],
                lastSeason=played[-1],
                bestWeek=games[-1],
                worstWeek=games[0],
            ),
            "seasons": [dict(record(by_season[team][y]), year=y) for y in played],
            "opponentHistory": sorted(
                (dict(record(versus[team][o]), opponent=o) for o in versus[team]),
                key=lambda r: (-r["winPercentage"], -r["gamesPlayed"], r["opponent"]),
            ),
        }

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "source": "NFL.com fantasy league 1078038, scraped 13 Nov 2022",
            "seasons": sorted(seasons),
            "games": sum(t["allTime"]["gamesPlayed"] for t in out.values()) // 2,
            "note": "2022 covers weeks 1-9 only; the rest of that season was unplayed when the data was scraped.",
        },
        "franchises": out,
    }
    with open(OUT / "league_records.json", "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    print(f"{payload['meta']['games']} games, {len(out)} franchises, {len(seasons)} seasons")


if __name__ == "__main__":
    main()
