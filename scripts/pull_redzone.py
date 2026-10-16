#!/usr/bin/env python3
"""
Pull play-by-play data from the season Google Sheets and publish the data the
two red zone tools need: player usage (targets, carries, touchdowns by yard
line) and team efficiency (trips, touchdown rate, points per trip).

Outputs (all under data/):
  redzone_<season>.json         per player-week targets, receptions, carries
                                and touchdowns in three yard-line bands, plus
                                every team's weekly totals for the share
                                columns
  redzone_index.json            which seasons exist + which is the default
  redzone_preload.html          crawlable player leaderboard for the fragment
  redzone_team_<season>.json    per team-week red zone trips, touchdowns,
                                field goals, points, plays, EPA, success,
                                turnovers, goal-to-go and inside-10 trips
  redzone_team_index.json       which seasons exist + which is the default
  redzone_team_preload.html     crawlable offense and defense tables

One read of each sheet feeds both pages. Both tools recompute everything in
the browser from the weekly cells, which is what lets the week range, the
zone toggle and the position filter work without a round trip.

Yard lines. `los` is yards to the opponent's goal line. A play is in the red
zone at 20 or closer. Counts are kept in three bands so the tool can show
inside the 20, inside the 10 and inside the 5 from one file:

    band 0   20 to 11
    band 1   10 to 6
    band 2    5 to 1

Inside the 10 is bands 1 + 2; inside the 20 is all three.

Opportunities. A target is a pass play with a TargetID (a sack or throwaway
has none). A carry is a rush play with a RusherID, scrambles included, so a
quarterback's designed runs and scrambles both count as carries. A target plus
a carry is an opportunity; not every target is caught, which is why the tool
says opportunities rather than touches. Kneels and spikes are excluded.
Two-point tries are not in the sheet.

Plays nullified by penalty. The provider's export already leaves those out:
every penalty row in the 2026 sheet is a play that stood, with the yardage
to the spot of the foul (a holding call beyond the line) or the foul tacked
on after the play. The guard in negated_by_penalty() drops a row only when
an accepted penalty of a play-cancelling kind was enforced from the previous
spot and the row carries no result and no yards, which is what a nullified
play would look like if a future export carried one.

Trips. A red zone trip is a drive with at least one pass or rush snap at 20
yards to goal or closer, kneels excluded, so an offense that kneels out at
the 15 is not charged a failed trip. A touchdown trip is one whose drive
ended in a touchdown; a field goal trip in a field goal. Points per trip
price a touchdown at 6 plus whatever the try added, read from the score on
the next snap of the game, and a field goal at 3, the box score tool's
pricing. Goal-to-go and inside-10 trips are the same idea with a tighter
qualifying snap.

Positions. The sheet tags the position of a targeted player and nothing
else. A player is a QB if he threw more passes than he had targets or
carries, otherwise his most common target tag (QB, RB, WR or TE), otherwise
a rusher who is never targeted is a RB. A two-way player tagged DB is a WR
here, a lineman who caught a tackle-eligible pass is a TE.

Standard library only — nothing to install, so CI stays fast.

Usage:
  python scripts/pull_redzone.py                          # current season only
  python scripts/pull_redzone.py --all                    # every season in config
  python scripts/pull_redzone.py --csv path.csv --season 2026 --out /tmp/rz   # local test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import offense  # noqa: E402
import preloads  # noqa: E402
import pull_matchup as pm  # noqa: E402
import pull_pace as pp  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
TOOL = "redzone"
TEAM_TOOL = "redzone_team"

# Fail loudly without these. The pull is useless if any is missing.
REQUIRED_COLUMNS = [
    "team", "opponent", "week", "down", "dist", "los", "PlayType", "PlayDesc",
    "PlayResult", "Yds", "EPA", "SuccessPlay", "DriveNumber", "DriveResult",
    "TargetID", "RusherID", "PasserID",
]
# Anything a row needs that an older sheet might not carry. A missing column
# degrades one feature rather than killing the pull: no TargetPos means every
# non-passer reads RB, no Cmp means receptions are blank.
OPTIONAL_COLUMNS = [
    "TargetPos", "TargetName", "RusherName", "PasserName", "Cmp", "Scramble?",
    "GameId", "PlayId", "TeamCurrentScore", "OppCurrentScore",
]

# Bumped whenever the shape of either season file changes, so a tool that
# needs the new shape never meets a half-converted archive.
SCHEMA = 1

WEEKS = 18
RED_ZONE = 20
BANDS = (20, 10, 5)           # the inner edge of each band; see the docstring
DEAD_BALL_RE = pm.DEAD_BALL_RE
GIVEAWAY_RESULTS = {"INT", "FUMBLE LOST", "DEF TD"}
SCORING_DRIVES = {"Touchdown": 6, "Field Goal": 3}
SKILL = ("QB", "RB", "WR", "TE")
# Tags the sheet uses for someone who is not a skill player. A defensive back
# who is targeted is a two-way player lined up as a receiver; anyone else
# (a lineman reporting eligible) is a tight end for the one catch.
TAG_FOLD = {"DB": "WR", "CB": "WR", "S": "WR", "OL": "TE", "T": "TE", "G": "TE",
            "C": "TE", "DL": "TE", "LB": "TE", "FB": "RB", "HB": "RB"}
# Hand corrections by player ID, applied last. Empty until a season proves
# the rules above wrong for someone.
POSITION_OVERRIDES = {}

# Penalties that cancel the play they were called on when accepted. Dead-ball
# and after-the-play fouls (unsportsmanlike conduct, taunting, a late hit) are
# not here: the play stands and the yards are tacked on. Intentional grounding
# is not here either: it is enforced from the previous spot but the pass
# attempt counts.
NEGATING_FOULS = re.compile(
    r"Offensive Holding|Defensive Holding|Illegal Contact|Pass Interference|"
    r"Illegal Formation|Illegal Shift|Illegal Motion|Ineligible Downfield|"
    r"Illegal Use of Hands|Illegal Block|Chop Block|Clipping|Tripping|Low Block|"
    r"Offside|Encroachment|Neutral Zone Infraction|Illegal Touch|Illegal Forward Pass",
    re.IGNORECASE)
PENALTY_RE = re.compile(
    r"PENALTY on ([A-Z]{2,3})(?:-\d+-\S+)? (.+?),? (\d+) yards?,? enforced at ([A-Z]{2,3}) (\d+)")

canonical_team = config.canonical_team
as_float = pp.as_float
as_int = pp.as_int
parse_week = pp.parse_week
truthy = pm.truthy


# ------------------------------------------------------------------------ io


def read_rows(text):
    """Return (rows, set of optional columns present), or (None, set()) if empty."""
    import csv
    import io
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if not fields:
        return None, set()
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise SystemExit("Sheet is missing required column(s): " + ", ".join(missing)
                         + "\nHeaders found: " + ", ".join(fields))
    return list(reader), {c for c in OPTIONAL_COLUMNS if c in fields}


def write_json(path, obj):
    text = json.dumps(obj, separators=(",", ":"), sort_keys=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


# --------------------------------------------------------------------- plays


def band_of(los):
    """0, 1 or 2 for a red zone snap, None outside the 20."""
    if los is None or los > RED_ZONE or los < 1:
        return None
    if los > BANDS[1]:
        return 0
    if los > BANDS[2]:
        return 1
    return 2


def negated_by_penalty(row, team):
    """True for a play an accepted penalty wiped out.

    The sheet does not mark these, so the test is the gamebook's: a
    play-cancelling foul enforced from the previous spot, on a row that
    carries no result and no yards. Enforcement spots are written from the
    side of the team whose territory it is, so the spot is converted to yards
    to goal before it is compared with `los`.
    """
    desc = row.get("PlayDesc") or ""
    if "PENALTY" not in desc:
        return False
    if (row.get("PlayResult") or "").strip():
        return False
    if (as_float(row.get("Yds")) or 0) != 0:
        return False
    los = as_float(row.get("los"))
    for m in PENALTY_RE.finditer(desc):
        if not NEGATING_FOULS.search(m.group(2)):
            continue
        spot_team, yard = canonical_team(m.group(4)), int(m.group(5))
        ytg = 100 - yard if spot_team == team else yard
        if los is not None and abs(ytg - los) < 0.5:
            return True
    return False


def plays_from_rows(rows, present):
    """One dict per usable pass or rush play, red zone or not. The player
    tables need the whole field for games played and positions; the team
    tables need every drive's snaps to find the trips."""
    plays = []
    dropped = Counter()
    has = present.__contains__
    for row in rows:
        ptype = (row.get("PlayType") or "").strip().upper()
        if ptype not in ("PASS", "RUSH"):
            dropped["not a pass or run"] += 1
            continue
        team = canonical_team(row.get("team"))
        opp = canonical_team(row.get("opponent"))
        week = parse_week(row.get("week"))
        if not team or not opp or week is None or not (1 <= week <= WEEKS):
            dropped["missing team or week"] += 1
            continue
        if negated_by_penalty(row, team):
            dropped["nullified by penalty"] += 1
            continue
        desc = row.get("PlayDesc") or ""
        kneel = bool(DEAD_BALL_RE.search(desc))
        los = as_float(row.get("los"))
        dist = as_float(row.get("dist"))
        result = (row.get("PlayResult") or "").strip().upper()
        scramble = has("Scramble?") and truthy(row.get("Scramble?"))
        target = (row.get("TargetID") or "").strip() if ptype == "PASS" else ""
        rusher = (row.get("RusherID") or "").strip() if ptype == "RUSH" else ""
        passer = (row.get("PasserID") or "").strip() if ptype == "PASS" else ""
        plays.append({
            "team": team, "opp": opp, "week": week,
            "game": (row.get("GameId") or "").strip() if has("GameId") else "",
            "order": as_int(row.get("PlayId")) if has("PlayId") else None,
            "drive": as_int(row.get("DriveNumber")),
            "drive_result": (row.get("DriveResult") or "").strip(),
            "score": as_int(row.get("TeamCurrentScore")) if has("TeamCurrentScore") else None,
            "opp_score": as_int(row.get("OppCurrentScore")) if has("OppCurrentScore") else None,
            "los": los, "band": band_of(los),
            "g2g": los is not None and dist is not None and dist >= los,
            "pass": ptype == "PASS", "dropback": ptype == "PASS" or scramble,
            "kneel": kneel,
            "td": result == "TD",
            "giveaway": result in GIVEAWAY_RESULTS,
            "epa": as_float(row.get("EPA")), "succ": as_int(row.get("SuccessPlay")),
            "target": target,
            "target_pos": (row.get("TargetPos") or "").strip().upper() if has("TargetPos") else "",
            "target_name": (row.get("TargetName") or "").strip() if has("TargetName") else "",
            "caught": has("Cmp") and truthy(row.get("Cmp")),
            "rusher": rusher,
            "rusher_name": (row.get("RusherName") or "").strip() if has("RusherName") else "",
            "passer": passer,
            "passer_name": (row.get("PasserName") or "").strip() if has("PasserName") else "",
        })
    return plays, dropped


# ------------------------------------------------------------------- players


def positions(plays):
    """{player id: position} for everyone who threw, was targeted or carried."""
    attempts = Counter()
    targets = Counter()
    carries = Counter()
    tags = defaultdict(Counter)
    for p in plays:
        if p["kneel"]:
            continue
        if p["passer"]:
            attempts[p["passer"]] += 1
        if p["target"]:
            targets[p["target"]] += 1
            tag = TAG_FOLD.get(p["target_pos"], p["target_pos"])
            if tag in SKILL:
                tags[p["target"]][tag] += 1
        if p["rusher"]:
            carries[p["rusher"]] += 1
    out = {}
    for pid in set(attempts) | set(targets) | set(carries):
        if attempts[pid] > targets[pid] and attempts[pid] > carries[pid]:
            pos = "QB"
        elif tags[pid]:
            pos = tags[pid].most_common(1)[0][0]
        else:
            pos = "RB"
        out[pid] = POSITION_OVERRIDES.get(pid, pos)
    return out


def empty_bands():
    # [targets, receptions, receiving TDs, carries, rushing TDs] per band
    return [[0, 0, 0, 0, 0] for _ in BANDS]


def player_weeks(plays):
    """({player: {"n": name, "p": pos, "t": team, "g": [weeks], "w": {week: cell}}},
        {team: {week: [opp, band cells...]}})

    A player cell is [team, band0, band1, band2] with each band
    [targets, receptions, receiving TDs, carries, rushing TDs]. A team cell is
    [opponent, band0, band1, band2] with each band
    [targets, carries, plays, dropbacks, TDs]. Only red zone weeks are stored;
    "g" lists every week the player had a target or a carry anywhere on the
    field, which is what the games column counts.
    """
    pos = positions(plays)
    names = {}
    last_seen = {}          # player -> (week, order, team)
    games = defaultdict(set)
    pw = defaultdict(lambda: defaultdict(lambda: None))
    tw = defaultdict(lambda: defaultdict(lambda: None))

    def cell(table, key, week, other):
        c = table[key][week]
        if c is None:
            c = table[key][week] = [other] + ([[0, 0, 0, 0, 0] for _ in BANDS])
        return c

    def note(pid, name, p):
        if name:
            names[pid] = name
        key = (p["week"], p["order"] if p["order"] is not None else 0)
        if pid not in last_seen or key >= last_seen[pid][:2]:
            last_seen[pid] = (key[0], key[1], p["team"])
        games[pid].add(p["week"])

    for p in plays:
        if p["kneel"]:
            continue
        if p["target"]:
            note(p["target"], p["target_name"], p)
        if p["rusher"]:
            note(p["rusher"], p["rusher_name"], p)
        b = p["band"]
        if b is None:
            continue
        t = cell(tw, p["team"], p["week"], p["opp"])[1 + b]
        t[2] += 1
        if p["dropback"]:
            t[3] += 1
        if p["td"]:
            t[4] += 1
        if p["target"]:
            t[0] += 1
            c = cell(pw, p["target"], p["week"], p["team"])[1 + b]
            c[0] += 1
            if p["caught"]:
                c[1] += 1
            if p["td"]:
                c[2] += 1
        if p["rusher"]:
            t[1] += 1
            c = cell(pw, p["rusher"], p["week"], p["team"])[1 + b]
            c[3] += 1
            if p["td"]:
                c[4] += 1

    players = {}
    for pid in sorted(pw):
        weeks = pw[pid]
        players[pid] = {
            "n": names.get(pid, pid),
            "p": pos.get(pid, "RB"),
            "t": last_seen[pid][2],
            "g": sorted(games[pid]),
            "w": {str(w): weeks[w] for w in sorted(weeks)},
        }
    teams = {}
    for team in sorted(tw):
        teams[team] = {str(w): tw[team][w] for w in sorted(tw[team])}
    return players, teams


# --------------------------------------------------------------------- teams


def try_points(scores, after_order, final):
    """The team's score on the game's first snap after `after_order`, from
    either team's rows, or the final score when the drive ended the game.
    None if nothing says."""
    for order, score in scores:
        if order > after_order and score is not None:
            return score
    return final


def team_weeks(plays, schedule):
    """{team: {week: [opp, trips, td_trips, fg_trips, pts, plays, dropbacks,
                      epa, succ, giveaways, g2g_trips, g2g_td, i10_trips, i10_td]}}

    The defense side is not stored: a defense's week is exactly the offense
    cell of the opponent it faced, and the cell carries the opponent code.
    """
    finals = {}
    for g in schedule or []:
        if g.get("as") is not None and g.get("hs") is not None:
            finals[(g["away"], g["w"])] = g["as"]
            finals[(g["home"], g["w"])] = g["hs"]

    # Every drive, kneels included, in snap order, so a touchdown drive can
    # read the score on the next snap of the game from either team's rows.
    drives = {}
    timeline = defaultdict(lambda: defaultdict(list))   # game -> team -> [(order, score)]
    for p in plays:
        if p["drive"] is None:
            continue
        key = (p["team"], p["week"], p["drive"])
        d = drives.get(key)
        order = p["order"] if p["order"] is not None else 0
        if d is None:
            d = drives[key] = {
                "team": p["team"], "week": p["week"], "opp": p["opp"], "game": p["game"],
                "result": p["drive_result"], "first": order, "last": order,
                "score": p["score"], "rz": False, "g2g": False, "i10": False,
            }
        d["last"] = max(d["last"], order)
        if order < d["first"]:
            d["first"] = order
            d["score"] = p["score"]
        if not p["kneel"]:
            if p["band"] is not None:
                d["rz"] = True
            if p["band"] is not None and p["band"] >= 1:
                d["i10"] = True
            if p["g2g"]:
                d["g2g"] = True
        if p["game"]:
            timeline[p["game"]][p["team"]].append((order, p["score"]))
            timeline[p["game"]][p["opp"]].append((order, p["opp_score"]))

    for game in timeline:
        for team in timeline[game]:
            timeline[game][team].sort()

    tw = defaultdict(lambda: defaultdict(lambda: None))

    def cell(team, week, opp):
        c = tw[team][week]
        if c is None:
            c = tw[team][week] = [opp, 0, 0, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0]
        return c

    for d in drives.values():
        if not d["rz"]:
            continue
        c = cell(d["team"], d["week"], d["opp"])
        c[1] += 1
        base = SCORING_DRIVES.get(d["result"])
        if base == 6:
            c[2] += 1
            after = try_points(timeline[d["game"]][d["team"]] if d["game"] else [],
                               d["last"], finals.get((d["team"], d["week"])))
            if d["score"] is None or after is None:
                c[4] += 7
            else:
                c[4] += 6 + max(0, min(2, after - d["score"] - 6))
        elif base == 3:
            c[3] += 1
            c[4] += 3
        if d["g2g"]:
            c[10] += 1
            if base == 6:
                c[11] += 1
        if d["i10"]:
            c[12] += 1
            if base == 6:
                c[13] += 1

    for p in plays:
        if p["band"] is None or p["kneel"]:
            continue
        c = cell(p["team"], p["week"], p["opp"])
        c[5] += 1
        if p["dropback"]:
            c[6] += 1
        if p["epa"] is not None:
            c[7] += p["epa"]
        if p["succ"]:
            c[8] += 1
        if p["giveaway"]:
            c[9] += 1

    out = {}
    for team in sorted(tw):
        out[team] = {}
        for week in sorted(tw[team]):
            c = tw[team][week]
            c[7] = round(c[7], 2)
            out[team][str(week)] = c
    return out


# ---------------------------------------------------------------- summaries
#
# The preload tables need season figures. The tools do the same sums in the
# browser; these exist so the crawlable table and the live table agree.


def bands_from(zone):
    """Which bands make up a zone: 20 -> all three, 10 -> the inner two, 5 -> the last."""
    return [i for i, edge in enumerate(BANDS) if edge <= zone]


def team_at(pl, w):
    """The team a player was on in week `w`, from his red zone weeks: the
    last one at or before it, else his first. Only matters for a player who
    changed teams."""
    known = sorted(int(k) for k in pl["w"])
    at = None
    for k in known:
        if k <= w:
            at = k
        else:
            break
    if at is None:
        at = known[0]
    return pl["w"][str(at)][0]


def player_summary(players, teams, zone=RED_ZONE, weeks=None):
    """Season totals per player inside `zone`. The share columns are read
    against the team's red zone targets, carries and touchdowns over EVERY
    game the team played (in `weeks`, if given), not only the games the
    player played, so a back who was on the field for two games does not
    read a 60% share of six carries. A player who changed teams is read
    against each team for the weeks he was on it."""
    use = bands_from(zone)
    out = {}
    for pid, pl in players.items():
        tg = rc = rtd = car = ctd = 0
        for w, c in pl["w"].items():
            if weeks is not None and int(w) not in weeks:
                continue
            for b in use:
                tg += c[1 + b][0]; rc += c[1 + b][1]; rtd += c[1 + b][2]
                car += c[1 + b][3]; ctd += c[1 + b][4]
        team_tg = team_car = team_td = 0
        for team in sorted({c[0] for c in pl["w"].values()}):
            for w, t in teams.get(team, {}).items():
                if weeks is not None and int(w) not in weeks:
                    continue
                if team_at(pl, int(w)) != team:
                    continue
                for b in use:
                    team_tg += t[1 + b][0]; team_car += t[1 + b][1]; team_td += t[1 + b][4]
        games = [g for g in pl["g"] if weeks is None or g in weeks]
        out[pid] = {
            "name": pl["n"], "pos": pl["p"], "team": pl["t"], "games": len(games),
            "tg": tg, "rc": rc, "car": car, "opp": tg + car, "td": rtd + ctd,
            "td_rate": (rtd + ctd) / (tg + car) if tg + car else None,
            "td_share": (rtd + ctd) / team_td if team_td else None,
            "tg_share": tg / team_tg if team_tg else None,
            "car_share": car / team_car if team_car else None,
        }
    return out


def team_summary(tw, teams):
    """Season offense and defense figures per team for the preload."""
    def blank():
        return {"g": 0, "trips": 0, "td": 0, "fg": 0, "pts": 0, "plays": 0, "db": 0,
                "epa": 0.0, "succ": 0, "to": 0}

    off = {t: blank() for t in teams}
    dfn = {t: blank() for t in teams}
    for team, weeks in tw.items():
        for w, c in weeks.items():
            for side, key in ((off, team), (dfn, c[0])):
                s = side.setdefault(key, blank())
                s["g"] += 1; s["trips"] += c[1]; s["td"] += c[2]; s["fg"] += c[3]
                s["pts"] += c[4]; s["plays"] += c[5]; s["db"] += c[6]
                s["epa"] += c[7]; s["succ"] += c[8]; s["to"] += c[9]
    return off, dfn


# ------------------------------------------------------------- static html


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def pct(v, dp=0):
    return "—" if v is None else f"{100 * v:.{dp}f}%"


def player_preload(season, players, teams, names, latest):
    """Top 50 by red zone opportunities, then the inside-the-5 carries list.
    Full team names so the long-tail "chargers red zone targets" searches land
    on real words rather than a code."""
    through = f" (through Week {latest})" if latest else ""
    s20 = player_summary(players, teams, RED_ZONE)
    top = sorted(s20.values(), key=lambda r: (-r["opp"], -r["td"], r["name"]))[:50]
    rows = []
    for i, r in enumerate(top, 1):
        rows.append(
            f'<tr><td>{i}</td><th scope="row">{esc(r["name"])}</th>'
            f'<td>{esc(names.get(r["team"], r["team"]))}</td><td>{r["pos"]}</td><td>{r["games"]}</td>'
            f'<td>{r["tg"]}</td><td>{r["rc"]}</td><td>{r["car"]}</td><td>{r["opp"]}</td>'
            f'<td>{r["td"]}</td><td>{pct(r["td_share"])}</td>'
            f'<td>{pct(r["tg_share"])}</td><td>{pct(r["car_share"])}</td></tr>'
        )
    main = (
        f'<table class="pt-pre"><caption>NFL Red Zone Targets and Carries by Player, '
        f'{season}{through}. Targets, receptions, carries and touchdowns on offensive '
        "snaps inside the opponent's 20-yard line, regular season, kneels and spikes "
        "excluded. Opportunities are targets plus carries. TD share, target share and "
        "carry share are the player's share of his team's red zone touchdowns, targets "
        "and carries over every game the team played. Games counts every game with a "
        "target or a carry anywhere on the field. Top 50 by opportunities.</caption>"
        '<thead><tr><th scope="col">Rank</th><th scope="col">Player</th>'
        '<th scope="col">Team</th><th scope="col">Pos</th><th scope="col">Games</th>'
        '<th scope="col">Red Zone Targets</th><th scope="col">Receptions</th>'
        '<th scope="col">Red Zone Carries</th><th scope="col">Opportunities</th>'
        '<th scope="col">TDs</th><th scope="col">TD Share</th>'
        '<th scope="col">Target Share</th><th scope="col">Carry Share</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )
    s5 = player_summary(players, teams, 5)
    top5 = sorted((r for r in s5.values() if r["car"] > 0),
                  key=lambda r: (-r["car"], -r["td"], r["name"]))[:20]
    rows = []
    for i, r in enumerate(top5, 1):
        rows.append(
            f'<tr><td>{i}</td><th scope="row">{esc(r["name"])}</th>'
            f'<td>{esc(names.get(r["team"], r["team"]))}</td><td>{r["pos"]}</td>'
            f'<td>{r["car"]}</td><td>{r["td"]}</td><td>{pct(r["car_share"])}</td></tr>'
        )
    goal = (
        f'<table class="pt-pre"><caption>Most Carries Inside the 5-Yard Line, {season}'
        f'{through}. Goal line carries and the touchdowns they produced, with each '
        "player's share of his team's carries inside the 5 over every game the team "
        "played. Top 20.</caption>"
        '<thead><tr><th scope="col">Rank</th><th scope="col">Player</th>'
        '<th scope="col">Team</th><th scope="col">Pos</th>'
        '<th scope="col">Carries Inside the 5</th><th scope="col">TDs</th>'
        '<th scope="col">Carry Share</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )
    return main + "\n" + goal


def team_preload(season, tw, teams, names, latest):
    through = f" (through Week {latest})" if latest else ""
    off, dfn = team_summary(tw, teams)

    def ratio(num, den, fmt):
        return fmt.format(num / den) if den else "—"

    def table(side, title, blurb, head_team, best_high):
        def td_rate(t):
            s = side[t]
            return (s["td"] / s["trips"]) if s["trips"] else None
        ranked = sorted(side, key=lambda t: (td_rate(t) is None,
                                            (-(td_rate(t) or 0)) if best_high else (td_rate(t) or 0),
                                            t))
        rows = []
        for i, t in enumerate(ranked, 1):
            s = side[t]
            n, pl = s["trips"], s["plays"]
            cells = [
                str(s["g"]), str(n), ratio(n, s["g"], "{:.1f}"),
                ratio(s["td"], n, "{:.0%}"), ratio(s["td"] + s["fg"], n, "{:.0%}"),
                ratio(s["pts"], n, "{:.2f}"), ratio(pl, n, "{:.1f}"),
                ratio(s["epa"], pl, "{:+.2f}"), ratio(s["succ"], pl, "{:.0%}"),
                ratio(s["db"], pl, "{:.0%}"), str(s["to"]),
            ]
            rows.append(f'<tr><td>{i}</td><th scope="row">{esc(names.get(t, t))}</th>'
                        + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        return (
            f'<table class="pt-pre"><caption>{title}, {season}{through}. {blurb}</caption>'
            f'<thead><tr><th scope="col">Rank</th><th scope="col">{head_team}</th>'
            '<th scope="col">Games</th><th scope="col">Red Zone Trips</th>'
            '<th scope="col">Trips per Game</th><th scope="col">TD %</th>'
            '<th scope="col">Scoring %</th><th scope="col">Points per Trip</th>'
            '<th scope="col">Plays per Trip</th><th scope="col">EPA per Play</th>'
            '<th scope="col">Success Rate</th><th scope="col">Pass Rate</th>'
            '<th scope="col">Turnovers</th></tr></thead>'
            "<tbody>" + "".join(rows) + "</tbody></table>"
        )

    blurb_o = ("A red zone trip is a drive with a snap inside the opponent's 20-yard line. "
               "TD % is the share of trips that ended in a touchdown, scoring % adds field "
               "goals, and points per trip prices a touchdown at six plus the try and a field "
               "goal at three. EPA, success rate and pass rate cover the snaps inside the 20. "
               "Ranked by TD %, best offense first.")
    blurb_d = ("The same figures for the offenses each defense faced. Ranked by TD % allowed, "
               "best defense first.")
    return (table(off, "NFL Red Zone Offense Stats", blurb_o, "Offense", True) + "\n" +
            table(dfn, "NFL Red Zone Defense Stats", blurb_d, "Defense", False))


# ------------------------------------------------------------------- season


def build_season(season, plays, dropped, schedule):
    teams = sorted({p["team"] for p in plays} | {p["opp"] for p in plays})
    latest = max(p["week"] for p in plays)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    players, ptw = player_weeks(plays)
    rz_plays = sum(1 for p in plays if p["band"] is not None and not p["kneel"])
    names = {t: config.team_name(t) for t in teams}
    player_payload = {
        "schema": SCHEMA, "season": season, "tool": TOOL, "generated_utc": stamp,
        "plays": rz_plays, "excluded": dict(dropped),
        "weeks": WEEKS, "latest_played_week": latest,
        "bands": list(BANDS),
        "teams": teams, "names": names,
        "players": players,
        "tw": ptw,
    }
    tw = team_weeks(plays, schedule)
    team_payload = {
        "schema": SCHEMA, "season": season, "tool": TEAM_TOOL, "generated_utc": stamp,
        "plays": rz_plays, "excluded": dict(dropped),
        "weeks": WEEKS, "latest_played_week": latest,
        "teams": teams, "names": names,
        "tw": tw,
    }
    return player_payload, team_payload


def publish(path, payload):
    """Write unless only the timestamp changed. Returns True if written."""
    stamp = payload.pop("generated_utc")
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            previous.pop("generated_utc", None)
            if previous == payload:
                payload["generated_utc"] = stamp
                return False
        except (json.JSONDecodeError, OSError):
            pass
    payload["generated_utc"] = stamp
    write_json(path, payload)
    return True


def write_index(prefix):
    known = []
    for path in sorted(DATA_DIR.glob(prefix + "_*.json")):
        stem = path.stem[len(prefix) + 1:]
        if stem.isdigit():
            known.append(int(stem))
    known.sort()
    write_json(DATA_DIR / f"{prefix}_index.json",
               {"seasons": known, "default": max(known) if known else None})


def load_text(season, args):
    if args.csv:
        return Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
    return pp.fetch_csv(season)


def season_plays(season, args):
    text = load_text(season, args)
    rows, present = read_rows(text)
    if not rows:
        return None, None, "sheet has no rows yet"
    rows, note = offense.offense_rows(rows)
    if note:
        print(f"{season}: {note}")
    for col in ("TargetPos", "Cmp", "Scramble?"):
        if col not in present:
            print(f"{season}: WARNING — no {col} column; see the docstring for what that costs.")
    plays, dropped = plays_from_rows(rows, present)
    if not plays:
        return None, None, f"{len(rows):,} rows but no usable plays"
    return plays, dropped, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="rebuild every season in config, not just the current one")
    ap.add_argument("--csv", help="read from a local CSV instead of the sheet (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    ap.add_argument("--out", help="write outputs here instead of data/ (testing)")
    args = ap.parse_args()

    global DATA_DIR
    if args.out:
        DATA_DIR = Path(args.out)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = config.CURRENT_SEASON
    if args.csv:
        seasons = [args.season or current]
    else:
        seasons = sorted(config.SEASON_SHEETS) if args.all else [current]

    newest = None
    for season in seasons:
        plays, dropped, reason = season_plays(season, args)
        if plays is None:
            print(f"{season}: {reason} — skipping. The season stays out of the index files.")
            continue
        # The matchup pull keeps a cached schedule per season; it prices the
        # try on a game-ending touchdown drive and nothing else, so a missing
        # file costs one point on a handful of drives, never the season.
        schedule = pm.load_schedule(REPO_ROOT / "data" / f"schedule_{season}.json")
        player_payload, team_payload = build_season(season, plays, dropped, schedule)
        if len(player_payload["teams"]) != 32:
            print(f"{season}: NOTE — {len(player_payload['teams'])} teams, not 32: "
                  f"{', '.join(player_payload['teams'])}. If one of those is an alternate "
                  f"spelling, add it to TEAM_ALIASES in scripts/config.py.")
        print(f"{season}: {len(plays):,} plays, {player_payload['plays']:,} in the red zone, "
              f"{len(player_payload['players']):,} players with red zone usage, "
              f"excluded {dict(dropped)}")
        for path, payload in ((DATA_DIR / f"{TOOL}_{season}.json", player_payload),
                              (DATA_DIR / f"{TEAM_TOOL}_{season}.json", team_payload)):
            print(f"{season}: {'wrote' if publish(path, payload) else 'no change in'} {path.name}")
        newest = (season, player_payload, team_payload)

    write_index(TOOL)
    write_index(TEAM_TOOL)

    if newest:
        season, pp_, tp = newest
        (DATA_DIR / f"{TOOL}_preload.html").write_text(
            player_preload(season, pp_["players"], pp_["tw"], pp_["names"], pp_["latest_played_week"]) + "\n",
            encoding="utf-8")
        (DATA_DIR / f"{TEAM_TOOL}_preload.html").write_text(
            team_preload(season, tp["tw"], tp["teams"], tp["names"], tp["latest_played_week"]) + "\n",
            encoding="utf-8")
        if preloads.write_manifest():
            print("Refreshed data/preloads.json.")


if __name__ == "__main__":
    main()
