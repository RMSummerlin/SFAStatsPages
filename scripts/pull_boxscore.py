#!/usr/bin/env python3
"""
Pull play-by-play from the season Google Sheet plus the nflverse schedule and
publish one box score per played game for the Box Score tool.

Outputs (all under data/):
  boxscore_<season>.json   every played game's two team lines (raw counters),
                           each team's season-to-date counters, the stat and
                           header definitions the tool renders from
  boxscore_index.json      which seasons exist + which is the default
  boxscore_preload.html    crawlable table for the latest played week
  schedule_<season>.json   cached nflverse schedule (shared with the matchup tool)

What a "box score" is here. The sheet carries pass and rush plays only, so this
is an offensive box score for each team: the official-looking counts (plays,
yards, first downs, third downs, turnovers, drives, time of possession) plus the
efficiency numbers the site is known for (EPA, success rate, explosives) and
the charting fields a normal box score cannot show (pressure, blitz, play
action, time to throw, coverage, yards before and after contact, personnel).
Special teams and penalty-only plays are not in the data and are not faked.

Everything is published as raw numerators and denominators. The tool divides,
so the same counters serve the game line, the season-to-date column and the
league average without three copies of the arithmetic.

Standard library only.

Usage:
  python scripts/pull_boxscore.py                       # current season
  python scripts/pull_boxscore.py --all                 # every season in config
  python scripts/pull_boxscore.py --csv export.csv --season 2026 \
      --schedule data/schedule_2026.json                # fully offline
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import offense  # noqa: E402
import preloads  # noqa: E402
import pull_matchup as pm  # noqa: E402  (sheet fetch, schedule fetch, parsers)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

TOOL = "boxscore"

REQUIRED_COLUMNS = [
    "team", "opponent", "week", "down", "dist", "PlayType", "PlayDesc",
    "EPA", "SuccessPlay", "Yds", "PlayResult",
]
# Anything a row needs that an older sheet might not carry. A missing column
# leaves that stat blank (the tool shows a dash) rather than killing the pull.
OPTIONAL_COLUMNS = [
    "Scramble?", "Sacked", "PFFPrsrAlwd", "Blitz?", "PFFCoverageType", "PlayAct",
    "AirYds", "Att", "Cmp", "TTT", "YdsPreCt", "YdsPostCt", "OffPers", "Shotgun",
    "Huddle", "los", "DriveNumber", "DriveResult", "DriveStartClock", "DriveEndClock",
    "DriveStartDist", "TeamCurrentScore", "PlayId", "PasserName",
]

DEAD_BALL_RE = pm.DEAD_BALL_RE
EXPLOSIVE_PASS = pm.EXPLOSIVE_PASS
EXPLOSIVE_RUSH = pm.EXPLOSIVE_RUSH
DEEP_AIR = pm.DEEP_AIR
MAN_COVERAGES = pm.MAN_COVERAGES
ZONE_COVERAGES = pm.ZONE_COVERAGES
WEEKS = pm.WEEKS
RED_ZONE = 20              # yards to goal
QUARTER_SECONDS = 900
CLOCK_RE = re.compile(r"^\s*(\d{1,2})?:?(\d{2})\s*$")

# A turnover is a play the offense ended without the ball: an interception, a
# lost fumble, or either returned for a score (PlayResult DEF TD). A fumble the
# offense recovered is PlayResult FUMBLE and is not one.
GIVEAWAY_RESULTS = {"INT", "FUMBLE LOST", "DEF TD"}
SCORING_DRIVES = {"Touchdown": 6, "Field Goal": 3}

# The rows of the box score, in display order. Each is a rate (num over den)
# or a count the tool renders from the published counters.
#   kind    how the tool formats it (see tool.html):
#           n     count                 yds   yards, a sum
#           pct   num/den as a percent  frac  "5/12" plus the percent
#           epa   EPA per play          epasum  EPA, a sum
#           r1    ratio, one decimal    r2    ratio, two decimals
#           sec   seconds, two decimals clock seconds as mm:ss
#           yl    yards to goal, shown as a yard line
#   hi_good True if more is better for the offense, False if less, None if it
#           is a tendency with no better side.
STATS = [
    # --- box score ---
    dict(key="plays",   group="box", label="Plays",               kind="n",     num="plays",      den=None,        hi_good=None),
    dict(key="yds",     group="box", label="Total yards",         kind="yds",   num="yds",        den=None,        hi_good=True),
    dict(key="ypp",     group="box", label="Yards per play",      kind="r1",    num="yds",        den="plays",     hi_good=True),
    dict(key="pyds",    group="box", label="Net passing yards",   kind="yds",   num="pass_yds",   den=None,        hi_good=True),
    dict(key="ryds",    group="box", label="Rushing yards",       kind="yds",   num="rush_yds",   den=None,        hi_good=True),
    dict(key="fd",      group="box", label="First downs",         kind="n",     num="fd",         den=None,        hi_good=True),
    dict(key="td",      group="box", label="Offensive touchdowns", kind="n",    num="td",         den=None,        hi_good=True),
    dict(key="third",   group="box", label="Third down",          kind="frac",  num="third_conv", den="third",     hi_good=True),
    dict(key="fourth",  group="box", label="Fourth down",         kind="frac",  num="fourth_conv", den="fourth",   hi_good=True),
    dict(key="to",      group="box", label="Turnovers",           kind="n",     num="to",         den=None,        hi_good=False),
    dict(key="drives",  group="box", label="Drives",              kind="n",     num="drives",     den=None,        hi_good=None),
    dict(key="ppd",     group="box", label="Points per drive",    kind="r2",    num="drive_pts",  den="drives",    hi_good=True),
    dict(key="start",   group="box", label="Average start",       kind="yl",    num="drive_start", den="drives",   hi_good=False),
    dict(key="rz",      group="box", label="Red zone TDs",        kind="frac",  num="rz_td",      den="rz_trips",  hi_good=True),
    dict(key="top",     group="box", label="Time of possession",  kind="clock", num="top",        den=None,        hi_good=True),
    # --- efficiency ---
    dict(key="epa",     group="eff", label="EPA per play",        kind="epa",   num="epa",        den="plays",     hi_good=True),
    dict(key="sr",      group="eff", label="Success rate",        kind="pct",   num="succ",       den="plays",     hi_good=True),
    dict(key="db_epa",  group="eff", label="EPA per dropback",    kind="epa",   num="db_epa",     den="db",        hi_good=True),
    dict(key="db_sr",   group="eff", label="Dropback success",    kind="pct",   num="db_succ",    den="db",        hi_good=True),
    dict(key="run_epa", group="eff", label="EPA per rush",        kind="epa",   num="run_epa",    den="run",       hi_good=True),
    dict(key="run_sr",  group="eff", label="Rush success",        kind="pct",   num="run_succ",   den="run",       hi_good=True),
    dict(key="early",   group="eff", label="Early-down success",  kind="pct",   num="early_succ", den="early",     hi_good=True),
    dict(key="explo",   group="eff", label="Explosive plays",     kind="n",     num="explo",      den=None,        hi_good=True),
    dict(key="explo_r", group="eff", label="Explosive play rate", kind="pct",   num="explo",      den="plays",     hi_good=True),
    dict(key="to_epa",  group="eff", label="Turnover EPA",        kind="epasum", num="to_epa",    den=None,        hi_good=True),
    # --- passing ---
    dict(key="cmp",     group="pass", label="Completions",        kind="frac",  num="cmp",        den="att",       hi_good=True),
    dict(key="nyd",     group="pass", label="Net yards per dropback", kind="r1", num="pass_yds",  den="pass_plays", hi_good=True),
    dict(key="adot",    group="pass", label="Average depth of target", kind="r1", num="air",      den="att",       hi_good=None),
    dict(key="deep",    group="pass", label="Deep target rate",   kind="pct",   num="deep",       den="att",       hi_good=None),
    dict(key="prsr",    group="pass", label="Pressure rate allowed", kind="pct", num="prsr",      den="db",        hi_good=False),
    dict(key="sack",    group="pass", label="Sack rate",          kind="pct",   num="sack",       den="db",        hi_good=False),
    dict(key="blitz",   group="pass", label="Blitz rate faced",   kind="pct",   num="blitz",      den="db",        hi_good=None),
    dict(key="pa",      group="pass", label="Play-action rate",   kind="pct",   num="pa",         den="db",        hi_good=None),
    dict(key="pa_epa",  group="pass", label="Play-action EPA",    kind="epa",   num="pa_epa",     den="pa",        hi_good=True),
    dict(key="ttt",     group="pass", label="Time to throw",      kind="sec",   num="ttt",        den="ttt_n",     hi_good=None),
    dict(key="man",     group="pass", label="Man coverage faced", kind="pct",   num="man",        den="cov",       hi_good=None),
    # --- rushing and tendencies ---
    dict(key="ypc",     group="run", label="Yards per carry",     kind="r1",    num="rush_yds",   den="rush_plays", hi_good=True),
    dict(key="ybc",     group="run", label="Yards before contact", kind="r1",   num="ybc",        den="ybc_n",     hi_good=True),
    dict(key="yac",     group="run", label="Yards after contact", kind="r1",    num="yac_run",    den="yac_n",     hi_good=True),
    dict(key="p11",     group="run", label="11 personnel",        kind="pct",   num="p11",        den="pers_n",    hi_good=None),
    dict(key="p12",     group="run", label="12 personnel",        kind="pct",   num="p12",        den="pers_n",    hi_good=None),
    dict(key="shotgun", group="run", label="Shotgun rate",        kind="pct",   num="shotgun",    den="sg_n",      hi_good=None),
    dict(key="nh",      group="run", label="No-huddle rate",      kind="pct",   num="nh",         den="huddle_n",  hi_good=None),
]
GROUPS = [
    dict(key="box",  label="Box score"),
    dict(key="eff",  label="Efficiency"),
    dict(key="pass", label="Passing"),
    dict(key="run",  label="Rushing and tendencies"),
]

# The diverging bars above the table: which team was better in each category
# and by how much. `scale` is the difference that fills the whole half-track;
# set from the spread of week-to-week game differences so a typical blowout
# reaches about three quarters of the way and only a freak game hits the end.
HEADER = [
    dict(key="sr",      label="Success rate",     short="SR",   scale=0.20),
    dict(key="epa",     label="EPA per play",     short="EPA",  scale=0.65),
    dict(key="db_epa",  label="Dropback EPA",     short="Pass", scale=1.00),
    dict(key="run_epa", label="Rush EPA",         short="Rush", scale=0.55),
    dict(key="explo",   label="Explosive plays",  short="Expl", scale=8),
    dict(key="prsr",    label="Pressure rate",    short="Prsr", scale=0.35),
    dict(key="to_epa",  label="Turnover EPA",     short="TO",   scale=18),
]
STAT_BY_KEY = {s["key"]: s for s in STATS}


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

as_float = pm.as_float
as_int = pm.as_int
parse_week = pm.parse_week
truthy = pm.truthy


def parse_clock(value):
    """'12:46' -> seconds remaining in the quarter. None if unparseable."""
    if value is None:
        return None
    m = CLOCK_RE.match(value)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2))


def drive_duration(start_clock, end_clock):
    """Elapsed seconds for a drive, handling the quarter boundary (as pull_pace)."""
    if start_clock is None or end_clock is None:
        return None
    if end_clock <= start_clock:
        return start_clock - end_clock
    return start_clock + (QUARTER_SECONDS - end_clock)


# ------------------------------------------------------------------- aggregate


def aggregate(rows, present, final_scores=None):
    """Per (team, week) counters for every play and drive stat.

    final_scores maps (team, week) -> that team's final score, used to price a
    team's last drive of the game (see drive_points). Returns
    (counters, opp_of, passers, n_used, excluded).
    """
    has = lambda c: c in present  # noqa: E731
    final_scores = final_scores or {}
    agg = defaultdict(lambda: defaultdict(float))
    opp_of = {}
    passers = defaultdict(lambda: defaultdict(int))
    drives = {}            # (team, week, drive) -> dict
    n_used = 0
    excluded = defaultdict(int)

    for row in rows:
        ptype = (row.get("PlayType") or "").strip().upper()
        if ptype not in ("PASS", "RUSH"):
            excluded["not pass or rush"] += 1
            continue
        team = config.canonical_team(row.get("team"))
        opp = config.canonical_team(row.get("opponent"))
        week = parse_week(row.get("week"))
        if not team or not opp or week is None:
            excluded["missing team or week"] += 1
            continue
        key = (team, week)
        opp_of[key] = opp
        # Drives are recorded before the kneel filter: a kneel-out drive is
        # still a drive, and its clock still counts toward possession.
        if has("DriveNumber") and has("DriveResult"):
            dno = as_int(row.get("DriveNumber"))
            if dno is not None:
                dkey = (team, week, dno)
                d = drives.get(dkey)
                if d is None:
                    d = drives[dkey] = {
                        "result": (row.get("DriveResult") or "").strip(),
                        "seconds": drive_duration(parse_clock(row.get("DriveStartClock")),
                                                  parse_clock(row.get("DriveEndClock")))
                                   if has("DriveStartClock") and has("DriveEndClock") else None,
                        "start": as_float(row.get("DriveStartDist")) if has("DriveStartDist") else None,
                        "score": as_int(row.get("TeamCurrentScore")) if has("TeamCurrentScore") else None,
                        "order": as_int(row.get("PlayId")) if has("PlayId") else None,
                        "rz": False,
                    }
                if has("los"):
                    los = as_float(row.get("los"))
                    if los is not None and los <= RED_ZONE:
                        d["rz"] = True
        if DEAD_BALL_RE.search(row.get("PlayDesc") or ""):
            excluded["kneel or spike"] += 1
            continue
        epa = as_float(row.get("EPA"))
        succ = as_int(row.get("SuccessPlay"))
        if epa is None or succ is None:
            excluded["missing EPA or success"] += 1
            continue
        n_used += 1

        yds = as_float(row.get("Yds")) or 0.0
        down = as_int(row.get("down"))
        dist = as_float(row.get("dist"))
        result = (row.get("PlayResult") or "").strip().upper()
        desc = (row.get("PlayDesc") or "").upper()
        scramble = has("Scramble?") and truthy(row.get("Scramble?"))
        dropback = ptype == "PASS" or scramble
        run = ptype == "RUSH" and not scramble
        is_pass = ptype == "PASS"
        converted = result in ("FIRST DOWN", "TD")

        c = agg[key]
        c["plays"] += 1; c["yds"] += yds; c["epa"] += epa; c["succ"] += succ
        if is_pass:
            c["pass_plays"] += 1; c["pass_yds"] += yds
        else:
            c["rush_plays"] += 1; c["rush_yds"] += yds
        if converted:
            c["fd"] += 1
        if result == "TD":
            c["td"] += 1
        if down in (1, 2):
            c["early"] += 1; c["early_succ"] += succ
        elif down == 3:
            c["third"] += 1; c["third_conv"] += converted
        elif down == 4:
            c["fourth"] += 1; c["fourth_conv"] += converted
        if result in GIVEAWAY_RESULTS:
            c["to"] += 1; c["to_epa"] += epa
            if "INTERCEPT" in desc:
                c["int"] += 1
            else:
                c["fum_lost"] += 1
        if (is_pass and yds >= EXPLOSIVE_PASS) or (ptype == "RUSH" and yds >= EXPLOSIVE_RUSH):
            c["explo"] += 1
        if dropback:
            c["db"] += 1; c["db_epa"] += epa; c["db_succ"] += succ
            if result == "SACK" or (has("Sacked") and (row.get("Sacked") or "").strip()):
                c["sack"] += 1
            if has("PFFPrsrAlwd") and truthy(row.get("PFFPrsrAlwd")):
                c["prsr"] += 1
            if has("Blitz?") and truthy(row.get("Blitz?")):
                c["blitz"] += 1
            if has("PFFCoverageType"):
                cov = (row.get("PFFCoverageType") or "").strip().upper()
                if cov in MAN_COVERAGES:
                    c["cov"] += 1; c["man"] += 1
                elif cov in ZONE_COVERAGES:
                    c["cov"] += 1
            if has("PlayAct") and truthy(row.get("PlayAct")):
                c["pa"] += 1; c["pa_epa"] += epa
            if is_pass and has("AirYds"):
                air = as_float(row.get("AirYds"))
                att = (not has("Att")) or truthy(row.get("Att"))
                if att and air is not None:
                    c["att"] += 1; c["air"] += air
                    if has("Cmp") and truthy(row.get("Cmp")):
                        c["cmp"] += 1
                    if air >= DEEP_AIR:
                        c["deep"] += 1
            if has("TTT"):
                t = as_float((row.get("TTT") or "").rstrip("s"))
                if t is not None and 0 < t < 15:
                    c["ttt"] += t; c["ttt_n"] += 1
        if run:
            c["run"] += 1; c["run_epa"] += epa; c["run_succ"] += succ
            if has("YdsPreCt"):
                v = as_float(row.get("YdsPreCt"))
                if v is not None:
                    c["ybc"] += v; c["ybc_n"] += 1
            if has("YdsPostCt"):
                v = as_float(row.get("YdsPostCt"))
                if v is not None:
                    c["yac_run"] += v; c["yac_n"] += 1
        if has("OffPers"):
            pers = (row.get("OffPers") or "").strip()
            if pers:
                c["pers_n"] += 1
                if pers == "11":
                    c["p11"] += 1
                elif pers == "12":
                    c["p12"] += 1
        if has("Shotgun"):
            c["sg_n"] += 1
            if truthy(row.get("Shotgun")):
                c["shotgun"] += 1
        if has("Huddle"):
            h = (row.get("Huddle") or "").strip().lower()
            if h:
                c["huddle_n"] += 1
                if h.startswith("no"):
                    c["nh"] += 1
        if is_pass and has("PasserName"):
            name = (row.get("PasserName") or "").strip()
            if name:
                passers[key][name] += 1

    fold_drives(agg, drives, final_scores)
    for c in agg.values():
        zero_fill(c, present)
    return agg, opp_of, passers, n_used, dict(excluded)


# Counters and the sheet column each depends on. A counter whose column is
# present is published as 0 when nothing incremented it (no turnovers is a
# number, not a gap); one whose column is absent is left out so the tool
# shows a dash.
ALWAYS = ["plays", "yds", "pass_plays", "pass_yds", "rush_plays", "rush_yds", "fd", "td",
          "third", "third_conv", "fourth", "fourth_conv", "to", "to_epa", "int", "fum_lost",
          "explo", "early", "early_succ", "epa", "succ", "db", "db_epa", "db_succ",
          "run", "run_epa", "run_succ", "sack"]
NEEDS = {
    "PFFPrsrAlwd": ["prsr"], "Blitz?": ["blitz"], "PFFCoverageType": ["man", "cov"],
    "PlayAct": ["pa", "pa_epa"], "AirYds": ["att", "air", "deep"], "Cmp": ["cmp"],
    "TTT": ["ttt", "ttt_n"], "YdsPreCt": ["ybc", "ybc_n"], "YdsPostCt": ["yac_run", "yac_n"],
    "OffPers": ["p11", "p12", "pers_n"], "Shotgun": ["shotgun", "sg_n"], "Huddle": ["nh", "huddle_n"],
    "DriveNumber": ["drives", "drive_pts"], "DriveStartClock": ["top", "top_n"],
    "DriveStartDist": ["drive_start", "start_n"], "los": ["rz_trips", "rz_td"],
}


def zero_fill(c, present):
    for k in ALWAYS:
        c.setdefault(k, 0)
    for col, keys in NEEDS.items():
        if col in present:
            for k in keys:
                c.setdefault(k, 0)


def drive_points(ordered, final_score):
    """Points each drive produced, from the team's own score before and after.

    A touchdown drive is worth 6 plus whatever the try added (the score on the
    team's next drive says whether the kick was good or a two-point try
    landed); a field goal drive is 3. The final score prices the last drive.
    Anything else is 0. Reading the score rather than assuming 7 keeps missed
    extra points honest; a defensive score between two drives can still add
    to the gap, so the try is capped at 2.
    """
    pts = []
    for i, d in enumerate(ordered):
        base = SCORING_DRIVES.get(d["result"])
        if base is None:
            pts.append(0)
            continue
        if base == 3:
            pts.append(3)
            continue
        after = ordered[i + 1]["score"] if i + 1 < len(ordered) else final_score
        if d["score"] is None or after is None:
            pts.append(7)
            continue
        pts.append(6 + max(0, min(2, after - d["score"] - 6)))
    return pts


def fold_drives(agg, drives, final_scores):
    by_team = defaultdict(list)
    for (team, week, dno), d in drives.items():
        by_team[(team, week)].append((d["order"] if d["order"] is not None else dno, dno, d))
    for key, lst in by_team.items():
        lst.sort(key=lambda x: (x[0], x[1]))
        ordered = [d for _, _, d in lst]
        c = agg[key]
        c["drives"] += len(ordered)
        for p in drive_points(ordered, final_scores.get(key)):
            c["drive_pts"] += p
        for d in ordered:
            if d["seconds"] is not None and 0 <= d["seconds"] <= QUARTER_SECONDS * 4:
                c["top"] += d["seconds"]; c["top_n"] += 1
            if d["start"] is not None:
                c["drive_start"] += d["start"]; c["start_n"] += 1
            if d["rz"]:
                c["rz_trips"] += 1
                if d["result"] == "Touchdown":
                    c["rz_td"] += 1


# ------------------------------------------------------------------- shaping


def clean(c):
    """Counters as plain numbers, ints where they are whole, sorted keys."""
    out = {}
    for k in sorted(c):
        v = c[k]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        elif isinstance(v, float):
            v = round(v, 3)
        out[k] = v
    return out


def stat_value(stat, c):
    num = c.get(stat["num"])
    if num is None:
        return None
    if stat["den"] is None:
        return num
    den = c.get(stat["den"])
    if not den:
        return None
    return num / den


def game_lines(agg, opp_of, passers, schedule):
    """One entry per game the sheet has both sides of, keyed by nflverse id."""
    games = {}
    unmatched = []
    have = set(agg)
    for g in schedule:
        a, h = (g["away"], g["w"]), (g["home"], g["w"])
        if a not in have or h not in have:
            continue
        if opp_of.get(a) != g["home"] or opp_of.get(h) != g["away"]:
            unmatched.append(f"week {g['w']} {g['away']} at {g['home']} (sheet says "
                             f"{g['away']} vs {opp_of.get(a)}, {g['home']} vs {opp_of.get(h)})")
            continue
        have.discard(a); have.discard(h)
        games[g["id"]] = {
            "w": g["w"],
            g["away"]: clean(agg[a]), g["home"]: clean(agg[h]),
            "qb": {g["away"]: top_passer(passers.get(a)), g["home"]: top_passer(passers.get(h))},
        }
    for team, week in sorted(have):
        unmatched.append(f"week {week} {team} vs {opp_of.get((team, week))} is in the sheet but not the schedule")
    return games, unmatched


def top_passer(d):
    if not d:
        return ""
    return max(d.items(), key=lambda kv: (kv[1], kv[0]))[0]


def season_totals(games, teams):
    tot = {t: defaultdict(float) for t in teams}
    for gid, g in games.items():
        for t in teams:
            if t in g:
                tot[t]["g"] += 1
                for k, v in g[t].items():
                    tot[t][k] += v
    return {t: clean(c) for t, c in tot.items() if c}


def league_totals(games):
    tot = defaultdict(float)
    for g in games.values():
        for k, v in g.items():
            if isinstance(v, dict) and k != "qb":
                tot["g"] += 1
                for kk, vv in v.items():
                    tot[kk] += vv
    return clean(tot)


# ------------------------------------------------------------- static html


def fmt(stat, c):
    v = stat_value(stat, c)
    if v is None:
        return "–"
    k = stat["kind"]
    if k == "n":
        return str(int(round(v)))
    if k == "yds":
        return str(int(round(v)))
    if k == "pct":
        return f"{round(v * 100)}%"
    if k == "frac":
        return f"{int(c.get(stat['num'], 0))}/{int(c.get(stat['den'], 0))}"
    if k == "epa":
        return "0.00" if round(v, 2) == 0 else f"{v:+.2f}"
    if k == "epasum":
        return "0.0" if round(v, 1) == 0 else f"{v:+.1f}"
    if k == "r1":
        return f"{v:.1f}"
    if k == "r2":
        return f"{v:.2f}"
    if k == "sec":
        return f"{v:.2f}s"
    if k == "clock":
        return f"{int(v // 60)}:{int(v % 60):02d}"
    if k == "yl":
        yl = 100 - v
        return f"Own {round(yl)}" if yl <= 50 else f"Opp {round(100 - yl)}"
    return str(v)


PRELOAD_KEYS = ["plays", "yds", "ypp", "fd", "third", "to", "top",
                "epa", "sr", "explo", "prsr", "ppd"]


def preload_table(season, W, schedule, games, names):
    rows = []
    for g in schedule:
        if g["w"] != W or g["id"] not in games:
            continue
        line = games[g["id"]]
        gcls = f"g-{g['away']}-{g['home']}".lower()
        for team, opp, ts, os_ in ((g["away"], g["home"], g["as"], g["hs"]),
                                   (g["home"], g["away"], g["hs"], g["as"])):
            c = line[team]
            res = ""
            if ts is not None and os_ is not None:
                res = ("W" if ts > os_ else "L" if ts < os_ else "T") + f" {ts}-{os_}"
            cells = "".join(f"<td>{fmt(STAT_BY_KEY[k], c)}</td>" for k in PRELOAD_KEYS)
            rows.append(f'<tr class="{gcls}"><th scope="row">{names.get(team, team)}</th>'
                        f"<td>{'vs' if g['neutral'] else ('at' if team == g['away'] else 'vs')} "
                        f"{names.get(opp, opp)}</td><td>{res}</td>{cells}</tr>")
    heads = "".join(f'<th scope="col">{STAT_BY_KEY[k]["label"]}</th>' for k in PRELOAD_KEYS)
    return (
        f'<table class="pt-pre"><caption>Week {W} NFL box scores for the {season} season: '
        "each offense's plays, yards, first downs, third downs, turnovers, time of possession, "
        "EPA per play, success rate, explosive plays, pressure rate allowed and points per drive. "
        "Pass and rush plays only; kneels and spikes excluded.</caption>"
        '<thead><tr><th scope="col">Team</th><th scope="col">Opponent</th><th scope="col">Result</th>'
        + heads + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


# ------------------------------------------------------------------------ main


def build_season(season, rows, present, schedule, today):
    final_scores = {}
    for g in schedule:
        if g["as"] is not None and g["hs"] is not None:
            final_scores[(g["away"], g["w"])] = g["as"]
            final_scores[(g["home"], g["w"])] = g["hs"]
    agg, opp_of, passers, n_used, excluded = aggregate(rows, present, final_scores)
    games, unmatched = game_lines(agg, opp_of, passers, schedule)
    for note in unmatched:
        print(f"{season}: NOTE {note}; not published")
    teams = sorted({t for t, w in agg})
    if len(teams) != 32:
        print(f"{season}: NOTE {len(teams)} teams, not 32: {', '.join(teams)}. "
              f"Check TEAM_ALIASES in scripts/config.py.")
    played = sorted({g["w"] for g in games.values()})
    latest = max(played) if played else 0
    cw = pm.current_week(schedule, today)
    names = {t: config.team_name(t) for t in teams}
    missing_cols = [c for c in OPTIONAL_COLUMNS if c not in present]
    if missing_cols:
        print(f"{season}: optional column(s) absent, those stats will show a dash: {', '.join(missing_cols)}")
    blob = {
        "season": season, "tool": TOOL,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "plays": n_used, "excluded": excluded,
        "current_week": cw, "latest_played_week": latest,
        "teams": teams, "names": names,
        "groups": GROUPS,
        "stats": [{k: v for k, v in s.items()} for s in STATS],
        "header": HEADER,
        "params": {"explosive_pass": EXPLOSIVE_PASS, "explosive_rush": EXPLOSIVE_RUSH,
                   "deep_air": DEEP_AIR, "red_zone": RED_ZONE},
        "schedule": schedule,
        "games": games,
        "season_totals": season_totals(games, teams),
        "league": league_totals(games),
    }
    preload = preload_table(season, latest, schedule, games, names) if latest else ""
    return blob, preload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild every season in config, not just the current one")
    ap.add_argument("--csv", help="read the season from a local CSV export (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    ap.add_argument("--schedule", help="local schedule JSON to use instead of fetching nflverse")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD) for the current-week pick")
    args = ap.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.csv:
        seasons = [args.season or config.CURRENT_SEASON]
    elif args.all:
        seasons = sorted(config.SEASON_SHEETS)
    else:
        seasons = [config.CURRENT_SEASON]
    today = args.today or date.today().isoformat()

    built = []
    for season in seasons:
        if args.csv:
            text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
        else:
            text = pm.fetch_csv(season)
        rows, present = read_rows(text) if text else (None, set())
        if not rows:
            print(f"{season}: sheet has no rows yet; skipping.")
            continue
        rows, note = offense.offense_rows(rows)
        if note:
            print(f"{season}: {note}")

        cache = DATA_DIR / f"schedule_{season}.json"
        if args.schedule:
            schedule = json.loads(Path(args.schedule).read_text(encoding="utf-8"))["games"]
        else:
            schedule = pm.fetch_schedule(season, cache)
        if not schedule:
            print(f"{season}: no schedule available and no cached copy; skipping. "
                  f"The tool keeps whatever was published last.")
            continue

        blob, preload = build_season(season, rows, present, schedule, today)
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
            print(f"{season}: no change ({blob['plays']:,} plays, {len(blob['games'])} games)")
        else:
            pm.write_json(out, blob)
            print(f"{season}: wrote {out.name}: {blob['plays']:,} plays, {len(blob['games'])} games, "
                  f"latest played week {blob['latest_played_week']}, current week {blob['current_week']}")
        if preload:
            built.append((season, preload))

    known = []
    for path in sorted(DATA_DIR.glob(f"{TOOL}_*.json")):
        parts = path.stem.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            known.append(int(parts[1]))
    known.sort()
    pm.write_json(DATA_DIR / f"{TOOL}_index.json", {"seasons": known, "default": max(known) if known else None})

    if built:
        season, preload = max(built)
        (DATA_DIR / f"{TOOL}_preload.html").write_text(preload + "\n", encoding="utf-8")
        if preloads.write_manifest():
            print("Refreshed data/preloads.json.")
        print("Refreshed the crawlable preload table in data/.")


if __name__ == "__main__":
    main()
