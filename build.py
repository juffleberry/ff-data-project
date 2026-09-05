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

# The 2022 scrape ran on 13 Nov 2022, midway through week 10, so weeks 10-16 came
# back as zeros and "Not yet played" placeholders. Those rows have been dropped
# from data/league_h2h.csv outright: an unplayed week is not a result. The
# season's real records survive in the NFL API archive, only its matchups are
# lost - which is why the regular-season length is read from those records
# rather than from the log.

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


def franchise_emoji():
    """The badge each franchise goes by, including ones that have left."""
    with open(RAW / "emoji.csv", newline="") as f:
        rows = csv.DictReader(r for r in f if not r.startswith("#"))
        return {r["franchise"]: r["emoji"] for r in rows if r.get("emoji")}


# ---------- game logs ----------

def regular_season_end(seasons):
    """Last week of the regular season, per year.

    Every team plays every regular-season week, so a team's regular-season games
    played is the number of weeks - and the season records state that directly.
    This used to be read off the game log as the run of weeks carrying a full
    slate, which agreed exactly but broke as soon as 2022's unplayed weeks were
    removed from the log. The records are the more direct source anyway.

    The league moved its playoff start between weeks 13 and 14 over the years,
    so it cannot be hardcoded.
    """
    out = {}
    for year, lg in seasons.items():
        weeks = {int(st["wins"]) + int(st["losses"]) + int(st["ties"])
                 for t in lg["teams"].values()
                 for st in [(t.get("stats") or {}).get("season", {}).get(year) or {}]
                 if st.get("record") and st["record"] != "0-0-0"}
        if weeks:
            out[year] = max(weeks)
    return out


def nfl_games(alias, reg_end):
    """Individual 2012-2022 matchups from the scrape, tagged regular or playoff."""
    with open(RAW / "league_h2h.csv", newline="") as f:
        for row in csv.DictReader(f):
            year, rnd = row["year"], int(row["round"])
            phase = "regular" if rnd <= reg_end.get(year, 99) else "playoff"
            yield (year, rnd, phase, alias[(year, row["home_team"])], float(row["home_score"]),
                   alias[(year, row["away_team"])], float(row["away_score"]))


def sleeper_games(alias):
    """Individual matchups from Sleeper, which pairs rosters by matchup_id."""
    for f in sorted(glob(str(RAW / "sleeper" / "*-matchups-*.json"))):
        year, week = re.search(r"(\d{4})-matchups-(\d+)", Path(f).name).groups()
        start = json.load(open(RAW / "sleeper" / f"{year}-league.json"))["settings"]["playoff_week_start"]
        phase = "regular" if int(week) < start else "playoff"
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
            yield (year, int(week), phase, alias[str(a["roster_id"])], float(a["points"]),
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

def playoff_bracket(seed, place):
    """Reconstruct the playoff pairings from seeds and final placings.

    The API never returned matchups, but it did return every team's playoff
    seed and its final placing, and those two together pin down the bracket:
    the teams placing 5th and 6th are exactly the ones that lost in round one,
    3rd and 4th are the semi-final losers, and 1st and 2nd contested the final.

    The league re-seeds between rounds - the top seed always draws the lowest
    surviving seed - which is what makes the reconstruction unique. Checked
    against the game log for 2012-2020: it reproduces all 46 playoff pairings
    exactly, 9 seasons out of 9. It gives no scores, only who played whom and
    who won.
    """
    by_seed = {v: k for k, v in seed.items()}
    at = {p: t for t, p in place.items()}
    n = len(seed)
    if n not in (4, 6) or sorted(seed.values()) != list(range(1, n + 1)):
        return []
    if len(at) != n:
        return []
    games = []
    if n == 6:
        out1 = {at[5], at[6]}
        alive = [by_seed[1], by_seed[2]]
        for a, b in ((by_seed[3], by_seed[6]), (by_seed[4], by_seed[5])):
            w = b if a in out1 else a
            games.append((a, b, w))
            alive.append(w)
        alive.sort(key=lambda t: seed[t])
        pairs = ((alive[0], alive[3]), (alive[1], alive[2]))
    else:
        pairs = ((by_seed[1], by_seed[4]), (by_seed[2], by_seed[3]))
    out2 = {at[3], at[4]}
    for a, b in pairs:
        games.append((a, b, b if a in out2 else a))
    games.append((at[1], at[2], at[1]))
    games.append((at[3], at[4], at[3]))
    return games


def brackets(seasons, alias, played):
    """Derived playoff pairings for every completed NFL season."""
    out = {}
    for year, lg in seasons.items():
        if year not in played or not lg.get("isSeasonOver"):
            continue
        seed, place = {}, {}
        for t in lg["teams"].values():
            st = (t.get("stats") or {}).get("season", {}).get(year) or {}
            if st.get("playoffBracketType") != "championship":
                continue
            name = alias[(year, t["name"])]
            if st.get("playoffSeed"):
                seed[name] = int(st["playoffSeed"])
            if st.get("place"):
                place[name] = int(st["place"])
        g = playoff_bracket(seed, place)
        if g:
            out[year] = g
    return out


def shitbowl():
    """Who came last in the consolation bracket, read from data/shitbowl.csv.

    Hand-maintained on purpose. NFL's API carries no consolation bracket detail,
    and its `place` field does not follow consolation results - in 2019 the seed
    that went 2-0 was placed 9th while the seed that went 0-3 was placed 8th, so
    there is nothing to solve against. For 2022-24 the postseason results are
    gone outright. Blank rows are left blank rather than guessed.
    """
    out = {}
    with open(RAW / "shitbowl.csv", newline="") as f:
        for row in csv.DictReader(r for r in f if not r.startswith("#")):
            if row.get("franchise"):
                out[row["year"]] = {
                    "franchise": row["franchise"],
                    "secondLast": row.get("second_last") or None,
                    "source": row.get("source") or None,
                }
    return out


def check_shitbowl(spoons, alias):
    """Fail loudly on a franchise name that doesn't exist.

    The file is typed by hand, so a stray "The Dirty Bird" would otherwise sail
    through and quietly render nothing.
    """
    known = set(alias.values())
    for year, v in spoons.items():
        for field in ("franchise", "secondLast"):
            name = v.get(field)
            if name and name not in known:
                raise SystemExit(
                    f"data/shitbowl.csv: {year} {field} {name!r} is not a franchise. "
                    f"Names must match data/franchises.csv."
                )


def finals(seasons, alias, played):
    """Champion, runner-up and podium for each season.

    finalStandingsTeamIds is the league's finishing order, 1st to 16th, and NFL
    kept it for every season including the three whose matchups are gone. It
    doesn't give scores, but it does settle who reached the final and who lost
    it - which no other surviving field says.
    """
    out = []
    for year, lg in sorted(seasons.items()):
        if year not in played or not lg.get("isSeasonOver"):
            continue
        by = {t["teamId"]: alias[(year, t["name"])] for t in lg["teams"].values()}
        order = [by[t] for t in (lg.get("finalStandingsTeamIds") or []) if t in by]
        if len(order) < 2:
            continue
        out.append({"year": year, "platform": "NFL.com", "order": order,
                    "champion": order[0], "runnerUp": order[1],
                    "third": order[2] if len(order) > 2 else None})
    return out


def sleeper_finals(alias):
    """Sleeper states the podium directly in the winners bracket."""
    out = []
    for f in sorted(glob(str(RAW / "sleeper" / "*-winners_bracket.json"))):
        year = re.match(r"(\d{4})", Path(f).name).group(1)
        place = {}
        for m in json.load(open(f)):
            if m.get("p") and m.get("w"):
                place[m["p"]] = alias[str(m["w"])]
                if m.get("l"):
                    place[m["p"] + 1] = alias[str(m["l"])]
        if 1 in place:
            out.append({"year": year, "platform": "Sleeper",
                        "order": [place[k] for k in sorted(place)],
                        "champion": place.get(1), "runnerUp": place.get(2), "third": place.get(3)})
    return out


def played_nfl(standings):
    return {s["year"] for s in standings if s["platform"] == "NFL.com"}


def sleeper_brackets(alias):
    """Sleeper states its bracket outright, so nothing needs reconstructing."""
    out = {}
    for f in sorted(glob(str(RAW / "sleeper" / "*-winners_bracket.json"))):
        year = re.match(r"(\d{4})", Path(f).name).group(1)
        gs = []
        for m in json.load(open(f)):
            if isinstance(m.get("t1"), int) and isinstance(m.get("t2"), int) and m.get("w"):
                gs.append((alias[str(m["t1"])], alias[str(m["t2"])], alias[str(m["w"])]))
        if gs:
            out[year] = gs
    return out


def blank():
    # scoredGames tracks how many of these games carry points. A reconstructed
    # playoff pairing has a winner but no score, so averaging over gamesPlayed
    # would quietly deflate every points-per-game figure it touches.
    return {"wins": 0, "losses": 0, "draws": 0, "pointsFor": 0.0, "pointsAgainst": 0.0,
            "scoredGames": 0}


def merged(by_phase, phase):
    """Opponent accumulators for one phase, or both phases added for 'combined'."""
    if phase != "combined":
        return by_phase[phase]
    out = defaultdict(blank)
    for p in ("regular", "playoff"):
        for opp, acc in by_phase[p].items():
            for k in out[opp]:
                out[opp][k] += acc[k]
    return out


def summarise(acc):
    games = acc["wins"] + acc["losses"] + acc["draws"]
    out = dict(acc, gamesPlayed=games)
    scored = acc.get("scoredGames", games)
    out["record"] = f"{acc['wins']}-{acc['losses']}-{acc['draws']}"
    # The original build wrote str(pct)[0:2] + '%', which truncates rather than
    # rounds, so every undefeated matchup rendered as "10%".
    out["winPercentage"] = round((acc["wins"] + acc["draws"] * 0.5) / games * 100, 1) if games else 0.0
    for k in ("pointsFor", "pointsAgainst"):
        out[k] = round(out[k], 2)
    out["avgPointsFor"] = round(out["pointsFor"] / scored, 2) if scored else 0.0
    out["avgPointsAgainst"] = round(out["pointsAgainst"] / scored, 2) if scored else 0.0
    return out


def main():
    seasons = nfl_seasons()
    alias, _ = franchises(seasons)
    salias = sleeper_alias()
    badge = franchise_emoji()
    reg_end = regular_season_end(seasons)

    standings = list(nfl_standings(seasons, alias)) + list(sleeper_standings(salias))
    # Which franchises reached the championship bracket in a given year. Games
    # played in a playoff week by a team that didn't are consolation games, and
    # belong to neither the regular season nor the playoffs.
    bracket = {(s["year"], s["franchise"]) for s in standings if s["madePlayoffs"]}

    games = list(nfl_games(alias, reg_end)) + list(sleeper_games(salias))

    # Scores for any playoff game the scrape did catch, so a derived pairing can
    # still carry real points where they survive.
    logged_scores = {}
    for year, rnd, phase, a, sa, b, sb in games:
        if phase == "playoff":
            logged_scores[(year, frozenset((a, b)))] = {a: sa, b: sb}

    # Playoff results come from the reconstructed brackets rather than the log.
    # The log is missing whole postseasons (2021's final is simply absent, and
    # the 2022 scrape stopped mid-December), while seeds and placings survive for
    # every completed season - so the bracket is the more complete source.
    derived = brackets(seasons, alias, played_nfl(standings))
    for year, sl in sorted(sleeper_brackets(salias).items()):
        derived[year] = sl

    overall = defaultdict(lambda: defaultdict(blank))          # [team][phase]
    versus = defaultdict(lambda: defaultdict(lambda: defaultdict(blank)))  # [team][phase][opp]
    per_season = defaultdict(lambda: defaultdict(blank))       # [(team, year)][phase]
    weeks = defaultdict(list)
    logged = set()

    for year, rnd, phase, a, sa, b, sb in games:
        logged.add(year)
        if phase == "playoff":
            continue  # counted from the brackets below, not the log
        for me, mine, them, theirs in ((a, sa, b, sb), (b, sb, a, sa)):
            # Recomputed from the scores: the scraped winner column fell through
            # to the away team on equal scores, filing every draw as an away win.
            res = "wins" if mine > theirs else "losses" if mine < theirs else "draws"
            for acc in (overall[me][phase], versus[me][phase][them], per_season[(me, year)][phase]):
                acc[res] += 1
                acc["scoredGames"] += 1
                acc["pointsFor"] += mine
                acc["pointsAgainst"] += theirs
            weeks[me].append({"points": round(mine, 2), "year": year, "round": rnd,
                              "opponent": them, "phase": phase})

    scored = set()
    for year, gs in derived.items():
        for a, b, winner in gs:
            pts = logged_scores.get((year, frozenset((a, b))))
            if pts:
                scored.add(year)
            for me, them in ((a, b), (b, a)):
                res = "wins" if me == winner else "losses"
                for acc in (overall[me]["playoff"], versus[me]["playoff"][them],
                            per_season[(me, year)]["playoff"]):
                    acc[res] += 1
                    if pts:
                        acc["scoredGames"] += 1
                        acc["pointsFor"] += pts[me]
                        acc["pointsAgainst"] += pts[them]

    by_team = defaultdict(list)
    for s in standings:
        by_team[s["franchise"]].append(s)

    current = max(s["year"] for s in standings if s["platform"] == "Sleeper")
    active = {s["franchise"] for s in standings if s["year"] == current}
    # 2026 has no results yet, so roster membership is the honest liveness test.
    live = json.load(open(RAW / "sleeper" / "2026-rosters.json"))
    active |= {salias[str(r["roster_id"])] for r in live}

    out = {}
    for name in sorted(by_team):
        yrs = sorted(by_team[name], key=lambda s: s["year"])
        # The regular-season career comes from the platforms' own season records,
        # which cover every year including the ones with no surviving game log.
        reg = blank()
        for s in yrs:
            reg["wins"] += s["wins"]
            reg["losses"] += s["losses"]
            reg["draws"] += s["ties"]
            reg["pointsFor"] += s["pointsFor"]
            reg["pointsAgainst"] += s["pointsAgainst"]
            reg["scoredGames"] += s["wins"] + s["losses"] + s["ties"]
        post = overall[name]["playoff"]
        # All-time is the two phases added, not a third source: the regular
        # season from the platforms' own records, the playoffs from the logs.
        both = blank()
        for src in (reg, post):
            for k in both:
                both[k] += src[k]

        for s in yrs:
            ps = per_season[(name, s["year"])]["playoff"]
            s["playoff"] = summarise(ps)

        wk = sorted(weeks.get(name, []), key=lambda w: w["points"])
        out[name] = {
            "franchise": name,
            "emoji": badge.get(name, ""),
            "active": name in active,
            "allTime": {
                "regular": summarise(reg),
                "playoff": summarise(post),
                "combined": summarise(both),
                "seasons": len(yrs),
                "firstSeason": yrs[0]["year"],
                "lastSeason": yrs[-1]["year"],
                "titles": sum(1 for s in yrs if s["finish"] == 1),
                "playoffAppearances": sum(1 for s in yrs if s["madePlayoffs"]),
                "adds": sum(s.get("adds", 0) for s in yrs),
                "trades": sum(s.get("trades", 0) for s in yrs),
                "bestWeek": wk[-1] if wk else None,
                "worstWeek": wk[0] if wk else None,
            },
            "seasons": yrs,
            "opponentHistory": {
                phase: sorted(
                    (dict(summarise(acc), opponent=o) for o, acc in merged(versus[name], phase).items()),
                    key=lambda r: (-r["winPercentage"], -r["gamesPlayed"], r["opponent"]),
                )
                for phase in ("regular", "playoff", "combined")
            },
        }

    OUT.mkdir(parents=True, exist_ok=True)
    with open(RAW / "franchises.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "team_name", "franchise"])
        w.writerows(sorted((y, n, fr) for (y, n), fr in alias.items()))

    # League-wide activity, so the dashboard doesn't have to re-derive it.
    activity = defaultdict(lambda: {"adds": 0, "trades": 0, "teams": 0, "platform": ""})
    for st in standings:
        a = activity[st["year"]]
        a["adds"] += st.get("adds", 0)
        a["trades"] += st.get("trades", 0)
        a["teams"] += 1
        a["platform"] = st["platform"]
    # A trade is counted once per team involved, so halve it for a league total.
    by_season = [dict(v, year=y, trades=v["trades"] // 2) for y, v in sorted(activity.items())]

    # Seasons that were actually played on NFL.com. The 2025 NFL league rolled
    # over when the league had already moved to Sleeper, so it carries a phantom
    # finishing order over an all-zero season; exclude it.
    played = {s["year"] for s in standings if s["platform"] == "NFL.com"}
    podiums = finals(seasons, alias, played) + sleeper_finals(salias)
    spoons = shitbowl()
    # Sleeper states it outright: the winner of the losers bracket's placement
    # final is the one crowned worst. Only counted once that game has been played,
    # so an in-progress season doesn't award the spoon early.
    for f in sorted(glob(str(RAW / "sleeper" / "*-losers_bracket.json"))):
        year = re.match(r"(\d{4})", Path(f).name).group(1)
        if year in spoons:
            continue
        for m in json.load(open(f)):
            if m.get("p") == 1 and m.get("w"):
                spoons[year] = {"franchise": salias[str(m["w"])], "secondLast": None,
                                "source": "sleeper-bracket"}
    check_shitbowl(spoons, alias)
    for f_ in podiums:
        sb = spoons.get(f_["year"])
        f_["shitbowl"] = sb["franchise"] if sb else None
        f_["shitbowlSecondLast"] = sb["secondLast"] if sb else None
        f_["shitbowlSource"] = sb["source"] if sb else None
    podium_by = defaultdict(dict)
    for f_ in podiums:
        for pos, who in enumerate(f_["order"], 1):
            podium_by[who][f_["year"]] = pos
    for name, t in out.items():
        won = sum(1 for f_ in podiums if f_["champion"] == name)
        lost = sum(1 for f_ in podiums if f_["runnerUp"] == name)
        t["allTime"]["finalsWon"] = won
        t["allTime"]["finalsLost"] = lost
        t["allTime"]["finalsReached"] = won + lost
        t["allTime"]["shitbowls"] = sum(1 for v in spoons.values() if v["franchise"] == name)
        for srow in t["seasons"]:
            sb = spoons.get(srow["year"])
            srow["shitbowl"] = bool(sb and sb["franchise"] == name)
        for srow in t["seasons"]:
            srow["finalStanding"] = podium_by[name].get(srow["year"])

    payload = {
        "meta": {
            "seasons": sorted({s["year"] for s in standings}),
            "matchupSeasons": sorted(logged),
            "regularSeasonEnd": dict(sorted(reg_end.items())),
            "bracketSeasons": sorted(derived),
            "shitbowlSeasons": sorted(spoons),
            "bracketScored": sorted(scored),
            "games": len(games),
            "franchises": len(out),
            "activityBySeason": by_season,
            "finals": podiums,
            "sources": [
                "NFL.com fantasy league 1078038 - game log scraped 13 Nov 2022",
                "api.fantasy.nfl.com - season standings, 2012-2024",
                "api.sleeper.app - leagues 1262684581069332480 (2025) and 1380142135487004672 (2026)",
            ],
            "note": ("Regular-season records come from the platforms' own season records and cover "
                     "every season. Playoff pairings are reconstructed from each team's seed and "
                     "final placing, which pin the bracket down uniquely; checked against the game "
                     "log, that reproduces all 46 playoff pairings for 2012-2020 exactly. Scores "
                     "attach only where the game log survives, so 2022, 2023 and 2024 playoff games "
                     "have a winner but no points. Regular-season matchups for 2022 wk10 to 2024 are "
                     "gone for good - only per-team season totals were ever exposed. Consolation "
                     "games count towards neither phase."),
        },
        "franchises": out,
    }
    with open(OUT / "league_records.json", "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    pl = sum(t["allTime"]["playoff"]["gamesPlayed"] for t in out.values()) // 2
    print(f"{len(out)} franchises · {len(standings)} team-seasons · {len(games)} logged games")
    print(f"regular-season end by year: {dict(sorted(reg_end.items()))}")
    print(f"playoff games reconstructed: {pl}")


if __name__ == "__main__":
    main()
