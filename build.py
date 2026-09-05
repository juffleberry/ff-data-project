#!/usr/bin/env python3
"""Build the league record book from every surviving source.

    python3 build.py

Sources, in the order they cover the league's history:

  data/league_h2h.csv        2012-2022 wk9. Individual game scores, scraped from
                             NFL.com in Nov 2022 before the platform shut down.
                             The only source with per-matchup detail for that era.
  data/nfl-api/*.json        2012-2024. Season standings straight from NFL's
                             fantasy API, which outlived the website. Final
                             records, points and placings - but no matchups.
  data/sleeper/*.json        2025 onwards, after the league moved to Sleeper.
                             Matchups and brackets, so head-to-head resumes.

Stdlib only. Writes docs/data/league_records.json.
"""
import csv
import json
import re
from collections import defaultdict
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data"
OUT = ROOT / "docs" / "data"
LEAGUE = "1078038"

# The 2022 scrape ran on 13 Nov 2022, midway through week 10. Weeks 10-16 came
# back as zeros and "Not yet played" placeholders. The NFL API still has the
# real final 2022 standings, so the season isn't lost - only its matchups are.
LAST_SCRAPED = ("2022", 9)
PLACEHOLDER = "Not yet played"

# A manager changing NFL accounts looks exactly like a new manager taking the
# seat. These two are the same person either side of the change; every other
# ownerUserId change in the league's history was a genuine handover.
SAME_MANAGER = {
    "3926061": "13638506",  # seat 2, moved accounts for 2016
    "3926444": "9158426",   # seat 3, co-managers swapped primary in 2015
}


# ---------- franchise identity ----------

def nfl_seasons():
    """{year: league dict} from the archived API responses."""
    out = {}
    for f in sorted(glob(str(RAW / "nfl-api" / "standings-*.json"))):
        y = re.search(r"(\d{4})", Path(f).name).group(1)
        out[y] = json.load(open(f))["games"][f"10{y}"]["leagues"][LEAGUE]
    return out


def franchises(seasons):
    """Map (year, team name) -> franchise, and franchise -> its display name.

    A franchise is one manager's continuous run in one team slot. Slots get
    handed on - slot 5 has had three different managers - so the slot alone
    isn't an identity, and neither is the team name, which changes most years.
    """
    runs, names = {}, defaultdict(dict)
    for y, lg in seasons.items():
        for t in lg["teams"].values():
            uid = SAME_MANAGER.get(t["ownerUserId"], t["ownerUserId"])
            key = (t["teamId"], uid)
            runs[(y, t["name"])] = key
            names[key][y] = t["name"]
    # Display name: the most recent name that was actually set. 'pending' is the
    # placeholder NFL shows for a manager who never named their team.
    label = {}
    for key, byyear in names.items():
        real = [n for _, n in sorted(byyear.items()) if n != "pending"]
        label[key] = real[-1]
    return {k: label[v] for k, v in runs.items()}, label


def sleeper_alias():
    """Sleeper roster id -> franchise display name, from the reviewed table."""
    with open(RAW / "sleeper_aliases.csv", newline="") as f:
        return {r["roster_id"]: r["franchise"] for r in csv.DictReader(f)}


# ---------- game logs ----------

def nfl_games(alias):
    """Individual 2012-2022 matchups from the scrape."""
    with open(RAW / "league_h2h.csv", newline="") as f:
        for row in csv.DictReader(f):
            year, rnd = row["year"], int(row["round"])
            if (year, rnd) > LAST_SCRAPED:
                continue
            if PLACEHOLDER in (row["home_team"], row["away_team"]):
                continue
            yield (year, rnd, alias[(year, row["home_team"])], float(row["home_score"]),
                   alias[(year, row["away_team"])], float(row["away_score"]))


def sleeper_games(alias):
    """Individual matchups from Sleeper, which pairs rosters by matchup_id."""
    for f in sorted(glob(str(RAW / "sleeper" / "*-matchups-*.json"))):
        year, week = re.search(r"(\d{4})-matchups-(\d+)", Path(f).name).groups()
        pairs = defaultdict(list)
        for m in json.load(open(f)):
            if m.get("matchup_id") is not None:
                pairs[m["matchup_id"]].append(m)
        for side in pairs.values():
            if len(side) != 2:
                continue
            a, b = side
            # An unplayed week comes back as a full slate of 0-0; skip it rather
            # than recording sixteen scoreless draws.
            if not a["points"] and not b["points"]:
                continue
            yield (year, int(week), alias[str(a["roster_id"])], float(a["points"]),
                   alias[str(b["roster_id"])], float(b["points"]))


# ---------- season standings ----------

def nfl_standings(seasons, alias):
    """Authoritative final records, including seasons the scrape never saw."""
    for y, lg in seasons.items():
        order = lg.get("finalStandingsTeamIds") or []
        for t in lg["teams"].values():
            s = (t.get("stats") or {}).get("season", {}).get(y) or {}
            if not s.get("record") or s["record"] == "0-0-0":
                continue
            yield {
                "year": y, "platform": "NFL.com", "franchise": alias[(y, t["name"])],
                "teamName": t["name"], "record": s["record"],
                "wins": int(s["wins"]), "losses": int(s["losses"]), "ties": int(s["ties"]),
                "pointsFor": round(float(s["pts"]), 2),
                "pointsAgainst": round(float(s["ptsAgainst"]), 2),
                "seasonRank": int(s["rank"]) if s.get("rank") else None,
                "finish": int(s["place"]) if s.get("place") else None,
                "playoffSeed": int(s["playoffSeed"]) if s.get("playoffSeed") else None,
                "madePlayoffs": s.get("playoffBracketType") == "championship",
                "finalOrder": order.index(t["teamId"]) + 1 if t["teamId"] in order else None,
                "adds": s.get("transactionAddCount") or 0,
                "trades": s.get("transactionTradeCount") or 0,
            }


def season_moves(year):
    """Completed adds and trades per roster, from the weekly transaction logs."""
    moves = defaultdict(lambda: {"adds": 0, "trades": 0})
    for f in sorted(glob(str(RAW / "sleeper" / f"{year}-transactions-*.json"))):
        for t in json.load(open(f)):
            if t.get("status") != "complete":
                continue
            for rid in t.get("roster_ids") or []:
                if t.get("type") == "trade":
                    moves[rid]["trades"] += 1
            for _, rid in (t.get("adds") or {}).items():
                moves[rid]["adds"] += 1
    return moves


def sleeper_standings(alias):
    """Sleeper keeps the running record on each roster; the bracket has the rest."""
    for f in sorted(glob(str(RAW / "sleeper" / "*-rosters.json"))):
        year = re.match(r"(\d{4})", Path(f).name).group(1)
        bracket_path = RAW / "sleeper" / f"{year}-winners_bracket.json"
        finish, in_bracket = {}, set()
        if bracket_path.exists():
            for m in json.load(open(bracket_path)):
                for side in ("t1", "t2", "w", "l"):
                    if isinstance(m.get(side), int):
                        in_bracket.add(m[side])
                if m.get("p") and m.get("w"):
                    finish[m["w"]] = m["p"]
                    if m.get("l"):
                        finish[m["l"]] = m["p"] + 1
        moves = season_moves(year)
        for r in json.load(open(f)):
            s = r.get("settings") or {}
            w, l, t = s.get("wins", 0), s.get("losses", 0), s.get("ties", 0)
            if not (w or l or t):
                continue
            yield {
                "year": year, "platform": "Sleeper", "franchise": alias[str(r["roster_id"])],
                "teamName": alias[str(r["roster_id"])], "record": f"{w}-{l}-{t}",
                "wins": w, "losses": l, "ties": t,
                "pointsFor": round(s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100, 2),
                "pointsAgainst": round(s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100, 2),
                "seasonRank": None,
                "finish": finish.get(r["roster_id"]),
                "playoffSeed": None,
                "madePlayoffs": r["roster_id"] in in_bracket,
                "finalOrder": None,
                "adds": moves[r["roster_id"]]["adds"],
                "trades": moves[r["roster_id"]]["trades"],
            }


# ---------- aggregation ----------

def blank():
    return {"wins": 0, "losses": 0, "draws": 0, "pointsFor": 0.0, "pointsAgainst": 0.0}


def summarise(acc):
    games = acc["wins"] + acc["losses"] + acc["draws"]
    out = dict(acc, gamesPlayed=games)
    out["record"] = f"{acc['wins']}-{acc['losses']}-{acc['draws']}"
    # The original build wrote str(pct)[0:2] + '%', which truncates rather than
    # rounds, so every undefeated matchup rendered as "10%".
    out["winPercentage"] = round((acc["wins"] + acc["draws"] * 0.5) / games * 100, 1) if games else 0.0
    for k in ("pointsFor", "pointsAgainst"):
        out[k] = round(out[k], 2)
    out["avgPointsFor"] = round(out["pointsFor"] / games, 2) if games else 0.0
    out["avgPointsAgainst"] = round(out["pointsAgainst"] / games, 2) if games else 0.0
    return out


def main():
    seasons = nfl_seasons()
    alias, _ = franchises(seasons)
    salias = sleeper_alias()

    games = list(nfl_games(alias)) + list(sleeper_games(salias))
    standings = list(nfl_standings(seasons, alias)) + list(sleeper_standings(salias))

    overall, versus, weeks = defaultdict(blank), defaultdict(lambda: defaultdict(blank)), defaultdict(list)
    logged = set()
    for year, rnd, a, sa, b, sb in games:
        logged.add(year)
        for me, mine, them, theirs in ((a, sa, b, sb), (b, sb, a, sa)):
            # Recomputed from the scores: the scraped winner column fell through
            # to the away team on equal scores, filing every draw as an away win.
            res = "wins" if mine > theirs else "losses" if mine < theirs else "draws"
            for acc in (overall[me], versus[me][them]):
                acc[res] += 1
                acc["pointsFor"] += mine
                acc["pointsAgainst"] += theirs
            weeks[me].append({"points": round(mine, 2), "year": year, "round": rnd, "opponent": them})

    by_team = defaultdict(list)
    for s in standings:
        by_team[s["franchise"]].append(s)

    out = {}
    for name in sorted(by_team):
        yrs = sorted(by_team[name], key=lambda s: s["year"])
        career = blank()
        for s in yrs:
            career["wins"] += s["wins"]
            career["losses"] += s["losses"]
            career["draws"] += s["ties"]
            career["pointsFor"] += s["pointsFor"]
            career["pointsAgainst"] += s["pointsAgainst"]
        wk = sorted(weeks.get(name, []), key=lambda w: w["points"])
        out[name] = {
            "franchise": name,
            "allTime": dict(
                summarise(career),
                seasons=len(yrs),
                firstSeason=yrs[0]["year"],
                lastSeason=yrs[-1]["year"],
                titles=sum(1 for s in yrs if s["finish"] == 1),
                adds=sum(s.get("adds", 0) for s in yrs),
                trades=sum(s.get("trades", 0) for s in yrs),
                playoffAppearances=sum(1 for s in yrs if s["madePlayoffs"]),
                bestWeek=wk[-1] if wk else None,
                worstWeek=wk[0] if wk else None,
            ),
            "seasons": yrs,
            "opponentHistory": sorted(
                (dict(summarise(versus[name][o]), opponent=o) for o in versus.get(name, {})),
                key=lambda r: (-r["winPercentage"], -r["gamesPlayed"], r["opponent"]),
            ),
        }

    # Emit the franchise map as a reviewable artefact. It is derived, not input,
    # but it is the one table a human would want to check by eye.
    with open(RAW / "franchises.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "team_name", "franchise"])
        w.writerows(sorted((y, n, fr) for (y, n), fr in alias.items()))

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "seasons": sorted({s["year"] for s in standings}),
            "matchupSeasons": sorted(logged),
            "games": len(games),
            "franchises": len(out),
            "sources": [
                "NFL.com fantasy league 1078038 — game log scraped 13 Nov 2022",
                "api.fantasy.nfl.com — season standings, 2012-2024",
                "api.sleeper.app — league 1262684581069332480 (2025) and 1380142135487004672 (2026)",
            ],
            "note": ("Season records cover every year. Head-to-head covers only the years "
                     "with a surviving game log: 2012 to 2022 week 9, and 2025 onward. "
                     "NFL's website was retired before 2022 wk10-2024 could be captured."),
        },
        "franchises": out,
    }
    with open(OUT / "league_records.json", "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"{len(out)} franchises · {len(standings)} team-seasons · {len(games)} logged games")
    print(f"seasons {payload['meta']['seasons'][0]}-{payload['meta']['seasons'][-1]}, "
          f"matchups for {', '.join(payload['meta']['matchupSeasons'])}")


if __name__ == "__main__":
    main()
