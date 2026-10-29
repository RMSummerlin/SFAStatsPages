#!/usr/bin/env python3
"""
Pull play-by-play from the current season's Google Sheet and publish two
crawlable tables for the first and anytime touchdown article:

  data/firsttd_team_preload.html    every team: games, times it scored the
                                    game's first touchdown, that rate, total
                                    touchdowns and offensive touchdowns,
                                    ranked by first touchdown rate
  data/firsttd_player_preload.html  every player who has scored a game's first
                                    touchdown: how many times, how many times
                                    his team's first touchdown, and his
                                    touchdowns in all, ranked by game firsts
  data/firsttd_<season>.json        the touchdowns behind them, game by game,
                                    for spot checks and for a future tool
  data/firsttd_index.json           which seasons exist + which is the default

Both tables reach the article through the shortcodes in
wordpress/sfa-preloads.php ([sharp_football_firsttd_team] and
[sharp_football_firsttd_player]); there is no interactive tool.

What counts. Every touchdown, however scored: an offensive touchdown is a
pass or rush row with PlayResult TD; a pick-six or fumble return is a pass or
rush row with PlayResult DEF TD, credited to the row's opponent; a kickoff,
punt or blocked field goal returned for a score is read from the gamebook
text of a KICKOFF, PUNT or FGA row, which carries no PlayResult. Extra point
and two-point rows never score a touchdown (a defensive return of one is two
points) and are skipped. Touchdowns within a game are ordered by quarter and
game clock, then PlayId, so the first is the first in time, not the first row.

Who scored. An offensive touchdown's scorer is the sheet's TargetName or
RusherName, the full name. A defensive or special teams scorer only exists in
the gamebook text, as "7-O.Oladejo", so the last player named before the
word TOUCHDOWN is taken and matched against the full names the sheet carries
for that team; a match gives the full name, otherwise the abbreviated one
stays. Defensive scorers are rarely the same person as an offensive one, so
in practice only returners who also catch passes get folded together.

Current season only: the article is a one-season snapshot, and the season
rolls over with config.CURRENT_SEASON. Standard library only.

Usage:
  python scripts/pull_firsttd.py                        # current season
  python scripts/pull_firsttd.py --csv export.csv --season 2026   # offline
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import offense  # noqa: E402
import preloads  # noqa: E402
import pull_matchup as pm  # noqa: E402  (sheet fetch, parsers)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

TOOL = "firsttd"

REQUIRED_COLUMNS = ["team", "opponent", "week", "PlayType", "PlayDesc", "PlayResult"]
# Without qtr and GameClock the touchdowns are ordered by PlayId alone; without
# the name columns every scorer is read from the gamebook text.
OPTIONAL_COLUMNS = ["qtr", "GameClock", "PlayId", "TargetName", "RusherName", "PasserName", "Scramble?"]

WEEKS = pm.WEEKS
as_int = pm.as_int
parse_week = pm.parse_week
truthy = pm.truthy

KICK_TYPES = {"KICKOFF", "PUNT", "FGA"}        # rows whose touchdown is in the text
NO_TD_TYPES = {"XPA", "TWOPOINTCONV"}          # a defensive return of a try is two points
CLOCK_RE = re.compile(r"^\s*(\d{1,2})?:?(\d{2})\s*$")
REVERSED_RE = re.compile(r"\bREVERSED\b")
RECOVERED_RE = re.compile(r"\b(?:RECOVERED|recovered) by ([A-Z]{2,3})-")
# A touchdown the gamebook took back on the same play.
NULLIFIED_RE = re.compile(r"\bNULLIFIED\b|\bNo Play\b", re.IGNORECASE)
# "7-O.Oladejo", "15-Ji.Horn", "11-J.Smith-Njigba", "14-A.St. Brown". The
# jersey number is required so a team code ("to HST 20") never reads as a
# name, and the second word is only taken when it starts a capitalised
# lower-case word, so "14-S.Diggs. PENALTY" stops at Diggs.
NAME_RE = re.compile(r"\b\d{1,2}-([A-Z][a-z]{0,2}\.\s?[A-Z][A-Za-z'\-]+(?:\.\s?(?=[A-Z][a-z])[A-Z][a-z]+)?)")
# Tacklers and the player who forced a fumble are written in parentheses,
# "FUMBLES (33-S.Neal)", and are never the scorer.
PAREN_RE = re.compile(r"\([^)]*\)")
SUFFIX_RE = re.compile(r"\s+(?:Jr|Sr|II|III|IV|V)\.?$")

# Fields published for every touchdown, in order.
KINDS = {"off": "offense", "def": "defense", "st": "special teams"}


# --------------------------------------------------------------------------- io


def read_rows(text: str):
    """Return (rows, optional columns present). rows is None for an empty sheet."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if not fields:
        return None, set()
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise SystemExit("Sheet is missing required column(s): " + ", ".join(missing)
                         + "\nHeaders found: " + ", ".join(fields))
    return list(reader), {c for c in OPTIONAL_COLUMNS if c in fields}


# ---------------------------------------------------------------------- parsing


def parse_clock(value):
    """'12:46' -> seconds remaining in the quarter. None if unparseable."""
    if value is None:
        return None
    m = CLOCK_RE.match(value)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2))


def final_text(desc):
    """The gamebook text after the last replay reversal: what actually stood."""
    return REVERSED_RE.split(desc or "")[-1]


def text_scorer(desc):
    """The last player named before TOUCHDOWN in the text that stood, as the
    gamebook writes him ("O.Oladejo"), or "" if none."""
    final = final_text(desc)
    i = final.find("TOUCHDOWN")
    if i < 0:
        return ""
    names = NAME_RE.findall(PAREN_RE.sub(" ", final[:i]))
    return names[-1] if names else ""


def text_touchdown(desc):
    """True when the text that stood scores a touchdown and does not take it
    back on the same play."""
    final = final_text(desc)
    return "TOUCHDOWN" in final and not NULLIFIED_RE.search(final)


def kick_scorer_team(ptype, desc, team, opp):
    """Which team scored on a kickoff, punt or field goal row. A recovery
    names the side that ended up with the ball; without one, a kickoff is
    returned by the row's team (the receiver owns the drive) and a punt or
    field goal by its opponent."""
    recovered = [config.canonical_team(code) for code in RECOVERED_RE.findall(final_text(desc))]
    if recovered and recovered[-1] in (team, opp):
        return recovered[-1]
    return team if ptype == "KICKOFF" else opp


def last_name(full):
    """'Amon-Ra St. Brown' -> 'St. Brown'; 'Marvin Harrison Jr.' -> 'Harrison'."""
    full = SUFFIX_RE.sub("", full.strip())
    parts = full.split(" ", 1)
    return parts[1] if len(parts) == 2 else full


def resolve_name(short, roster):
    """'J.Pitre' -> 'Jalen Pitre' when exactly one name on the team's roster
    starts with that initial and ends with that surname; else the short form."""
    if "." not in short:
        return short
    initial, rest = short.split(".", 1)
    rest = rest.strip()
    hits = {full for full in roster
            if full.split(" ", 1)[0].startswith(initial) and last_name(full) == rest}
    return hits.pop() if len(hits) == 1 else short


# ------------------------------------------------------------------- touchdowns


def touchdowns(rows, present):
    """Every touchdown in the sheet plus what the tables need around them.

    Returns (tds, games_played, rosters, n_plays, excluded):
      tds           list of dicts: game, week, team (who scored), scorer, kind,
                    order (sortable within the game), qtr, clock
      games_played  {team: set of weeks with a pass or rush snap}
      rosters       {team: set of full names the sheet carries}
      n_plays       pass and rush rows read
      excluded      row counts by reason, for the status page
    """
    present = set(present)
    has = present.__contains__
    tds = []
    games_played = defaultdict(set)
    rosters = defaultdict(set)
    n_plays = 0
    excluded = defaultdict(int)

    for i, row in enumerate(rows):
        ptype = (row.get("PlayType") or "").strip().upper()
        team = config.canonical_team(row.get("team"))
        opp = config.canonical_team(row.get("opponent"))
        week = parse_week(row.get("week"))
        if not team or not opp or week is None or not 1 <= week <= WEEKS:
            excluded["missing team or week"] += 1
            continue
        desc = row.get("PlayDesc") or ""
        result = (row.get("PlayResult") or "").strip().upper()

        if ptype in ("PASS", "RUSH"):
            n_plays += 1
            games_played[team].add(week)
            games_played[opp].add(week)
            for col in ("TargetName", "RusherName", "PasserName"):
                if has(col):
                    name = (row.get(col) or "").strip()
                    if name:
                        rosters[team].add(name)
            if result == "TD":
                scored, kind, scorer = team, "off", ""
                if "FUMBLE" not in desc.upper():        # else a teammate fell on it: read the text
                    if ptype == "PASS":
                        scorer = (row.get("TargetName") or "").strip() if has("TargetName") else ""
                    else:
                        scorer = (row.get("RusherName") or "").strip() if has("RusherName") else ""
                        if not scorer and has("PasserName") and has("Scramble?") and truthy(row.get("Scramble?")):
                            scorer = (row.get("PasserName") or "").strip()
            elif result == "DEF TD":
                scored, kind, scorer = opp, "def", ""
            else:
                continue
        elif ptype in KICK_TYPES:
            excluded["special teams"] += 1
            if not text_touchdown(desc):
                continue
            scored, kind, scorer = kick_scorer_team(ptype, desc, team, opp), "st", ""
        elif ptype in NO_TD_TYPES:
            excluded["special teams"] += 1
            continue
        else:
            excluded["not pass or rush"] += 1
            continue

        # Only the text names a defensive or special teams scorer. It is kept
        # on those touchdowns in the season file so an editor can check the
        # read against the gamebook.
        from_text = not scorer
        if from_text:
            scorer = text_scorer(desc)
        qtr = as_int(row.get("qtr")) if has("qtr") else None
        clock = parse_clock(row.get("GameClock")) if has("GameClock") else None
        pid = as_int(row.get("PlayId")) if has("PlayId") else None
        tds.append({
            "game": (week,) + tuple(sorted((team, opp))),
            "week": week, "team": scored, "opp": team if scored == opp else opp,
            "scorer": scorer, "kind": kind,
            "text": final_text(desc).strip() if from_text else "",
            "qtr": qtr, "clock": clock,
            # Quarter and clock first, PlayId as the tie-break, row order last.
            "order": (qtr if qtr is not None else 0,
                      -clock if clock is not None else 0,
                      pid if pid is not None else i, i),
        })
    return tds, games_played, dict(rosters), n_plays, dict(excluded)


def by_game(tds):
    """{game key: touchdowns in time order}."""
    games = defaultdict(list)
    for td in tds:
        games[td["game"]].append(td)
    for lst in games.values():
        lst.sort(key=lambda td: td["order"])
    return dict(games)


def summarise(tds, games_played, rosters):
    """(teams, players) for the two tables.

    teams: {team: {g, first, td, off}}; players: {(team, name): {first,
    first_team, td}}, every scorer, with first the game's first touchdowns
    and first_team the team's own (which include the game's)."""
    teams = {t: {"g": len(ws), "first": 0, "td": 0, "off": 0} for t, ws in games_played.items()}
    players = defaultdict(lambda: {"first": 0, "first_team": 0, "td": 0})
    for td in tds:
        td["scorer"] = resolve_name(td["scorer"], rosters.get(td["team"], ())) if td["scorer"] else ""
    for game, lst in by_game(tds).items():
        seen = set()
        for n, td in enumerate(lst):
            t = teams.setdefault(td["team"], {"g": 0, "first": 0, "td": 0, "off": 0})
            t["td"] += 1
            if td["kind"] == "off":
                t["off"] += 1
            p = players[(td["team"], td["scorer"] or "Unknown")]
            p["td"] += 1
            if n == 0:
                t["first"] += 1
                p["first"] += 1
            if td["team"] not in seen:
                seen.add(td["team"])
                p["first_team"] += 1
    return teams, dict(players)


# ------------------------------------------------------------- static html


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def team_preload(season, teams, names, latest):
    through = f" (through Week {latest})" if latest else ""

    def rate(t):
        return teams[t]["first"] / teams[t]["g"] if teams[t]["g"] else 0.0

    ranked = sorted(teams, key=lambda t: (-rate(t), -teams[t]["first"], -teams[t]["td"], t))
    rows = []
    for t in ranked:
        s = teams[t]
        rows.append(f'<tr><th scope="row">{esc(names.get(t, t))}</th><td>{s["g"]}</td>'
                    f'<td>{s["first"]}</td><td>{rate(t):.0%}</td><td>{s["td"]}</td><td>{s["off"]}</td></tr>')
    return (
        f'<table class="pt-pre"><caption>NFL First Touchdown Rate by Team, {season}{through}. '
        "How often each team scored the first touchdown of the game this season, over the "
        "games it has played. Every touchdown counts: offensive, defensive and special teams. "
        "Ranked by first touchdown rate.</caption>"
        '<thead><tr><th scope="col">Team</th><th scope="col">Games</th>'
        '<th scope="col">First TD</th><th scope="col">First TD Rate</th>'
        '<th scope="col">Total TDs</th><th scope="col">Offensive TDs</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def player_preload(season, players, latest):
    through = f" (through Week {latest})" if latest else ""
    ranked = sorted(((k, p) for k, p in players.items() if p["first"] > 0),
                    key=lambda kp: (-kp[1]["first"], -kp[1]["first_team"], -kp[1]["td"], kp[0][1], kp[0][0]))
    rows = []
    for (team, name), p in ranked:
        rows.append(f'<tr><th scope="row">{esc(name)} ({esc(team)})</th>'
                    f'<td>{p["first"]}</td><td>{p["first_team"]}</td><td>{p["td"]}</td></tr>')
    return (
        f'<table class="pt-pre"><caption>NFL First Touchdown Scorers, {season}{through}. '
        "Every player who has scored the first touchdown of a game this season: how many "
        "times he scored the game's first touchdown, how many times his team's first "
        "touchdown (which includes the game's), and his touchdowns in all. Every touchdown "
        "counts, offensive, defensive and special teams. Ranked by first touchdowns in a "
        "game.</caption>"
        '<thead><tr><th scope="col">Player</th><th scope="col">First TD</th>'
        '<th scope="col">First Team TD</th><th scope="col">Total TDs</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


# ------------------------------------------------------------------------ main


def build_season(season, rows, present):
    tds, games_played, rosters, n_plays, excluded = touchdowns(rows, present)
    teams, players = summarise(tds, games_played, rosters)
    latest = max((w for ws in games_played.values() for w in ws), default=0)
    names = {t: config.team_name(t) for t in sorted(teams)}
    if len(teams) != 32:
        print(f"{season}: NOTE {len(teams)} teams, not 32: {', '.join(sorted(teams))}. "
              f"Check TEAM_ALIASES in scripts/config.py.")
    missing = [c for c in OPTIONAL_COLUMNS if c not in present]
    if missing:
        print(f"{season}: optional column(s) absent: {', '.join(missing)}")
    unnamed = sum(1 for td in tds if not td["scorer"])
    if unnamed:
        print(f"{season}: NOTE {unnamed} touchdown(s) with no scorer read; listed as Unknown")
    games = []
    for key, lst in sorted(by_game(tds).items()):
        games.append({"week": key[0], "teams": list(key[1:]),
                      "tds": [dict({"team": td["team"], "scorer": td["scorer"], "kind": td["kind"],
                                    "qtr": td["qtr"], "clock": td["clock"]},
                                   **({"text": td["text"]} if td["text"] else {})) for td in lst]})
    blob = {
        "season": season, "tool": TOOL,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "plays": n_plays, "excluded": excluded,
        "touchdowns": len(tds), "latest_played_week": latest,
        "names": names,
        "teams": {t: teams[t] for t in sorted(teams)},
        "players": [{"team": k[0], "name": k[1], **p} for k, p in
                    sorted(players.items(), key=lambda kp: (-kp[1]["first"], -kp[1]["first_team"], -kp[1]["td"], kp[0][1]))],
        "games": games,
    }
    return blob, team_preload(season, teams, names, latest), player_preload(season, players, latest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="read the season from a local CSV export (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    args = ap.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    season = (args.season or config.CURRENT_SEASON) if args.csv else config.CURRENT_SEASON

    if args.csv:
        text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
    else:
        text = pm.fetch_csv(season)
    rows, present = read_rows(text) if text else (None, set())
    if not rows:
        print(f"{season}: sheet has no rows yet; skipping.")
        return
    rows, note = offense.offense_rows(rows)
    if note:
        print(f"{season}: {note}")

    blob, team_html, player_html = build_season(season, rows, present)
    out = DATA_DIR / f"{TOOL}_{season}.json"
    stamp = blob.pop("generated_utc")
    blob = json.loads(json.dumps(blob))
    unchanged = False
    if out.exists():
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
            previous.pop("generated_utc", None)
            unchanged = previous == blob
        except (json.JSONDecodeError, OSError):
            pass
    blob["generated_utc"] = stamp
    if unchanged:
        print(f"{season}: no change ({blob['touchdowns']} touchdowns in {len(blob['games'])} games)")
    else:
        pm.write_json(out, blob)
        print(f"{season}: wrote {out.name}: {blob['touchdowns']} touchdowns in {len(blob['games'])} games, "
              f"latest played week {blob['latest_played_week']}")

    known = sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob(f"{TOOL}_*.json")
                   if len(p.stem.split("_")) == 2 and p.stem.split("_")[1].isdigit())
    pm.write_json(DATA_DIR / f"{TOOL}_index.json", {"seasons": known, "default": max(known) if known else None})

    # The crawlable tables are the newest season's. A --csv run for an older
    # season must not overwrite them.
    if season == max(known):
        (DATA_DIR / f"{TOOL}_team_preload.html").write_text(team_html + "\n", encoding="utf-8")
        (DATA_DIR / f"{TOOL}_player_preload.html").write_text(player_html + "\n", encoding="utf-8")
        if preloads.write_manifest():
            print("Refreshed data/preloads.json.")
        print("Refreshed the two crawlable preload tables in data/.")
    else:
        print(f"{season}: not the newest season on disk; preload tables left as {max(known)}'s.")


if __name__ == "__main__":
    main()
