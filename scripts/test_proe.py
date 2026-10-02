#!/usr/bin/env python3
"""
Regression tests for pull_proe.py.

    python scripts/test_proe.py

No network and no data files. The workflow runs every scripts/test_*.py before
the pull step, so a failure here stops a bad build before it can commit data.

Each test exists because the obvious implementation is wrong in a way that
would not announce itself in the output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pull_matchup as pm  # noqa: E402
import pull_proe as P  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


# ------------------------------------------------------------------ buckets
#
# The bands are the whole definition of "the same situation", so a boundary
# that drifts changes every number in the tool without anything failing.

check("dist 1", P.dist_band(1), "d1")
check("dist 0 (goal line restart)", P.dist_band(0), "d1")
check("dist 3", P.dist_band(3), "d2")
check("dist 4", P.dist_band(4), "d4")
check("dist 6", P.dist_band(6), "d4")
check("dist 7", P.dist_band(7), "d7")
check("dist 9", P.dist_band(9), "d7")
check("dist 10 is its own band", P.dist_band(10), "d10")
check("dist 11", P.dist_band(11), "d11")
check("dist 36", P.dist_band(36), "d11")

check("own 1", P.field_zone(99), "A")
check("own 20", P.field_zone(80), "A")
check("own 21", P.field_zone(79), "B")
check("midfield", P.field_zone(50), "B")
check("opp 49", P.field_zone(49), "C")
check("opp 21", P.field_zone(21), "C")
check("opp 20 is the red zone", P.field_zone(20), "D")
check("opp 1", P.field_zone(1), "D")

check("Q1", P.clock_state(1, 10), "h1")
check("Q2 2:01", P.clock_state(2, 121), "h1")
check("Q2 2:00", P.clock_state(2, 120), "h1l")
check("Q3 0:30", P.clock_state(3, 30), "q3")
check("Q4 4:01", P.clock_state(4, 241), "q4")
check("Q4 4:00", P.clock_state(4, 240), "late")
check("overtime", P.clock_state(5, 600), "late")

check("down 17", P.margin_band(-17), "m3")
check("down 16", P.margin_band(-16), "m2")
check("down 9", P.margin_band(-9), "m2")
check("down 8", P.margin_band(-8), "m1")
check("down 4", P.margin_band(-4), "m1")
check("down 3", P.margin_band(-3), "e")
check("tied", P.margin_band(0), "e")
check("up 3", P.margin_band(3), "e")
check("up 4", P.margin_band(4), "p1")
check("up 8", P.margin_band(8), "p1")
check("up 9", P.margin_band(9), "p2")
check("up 16", P.margin_band(16), "p2")
check("up 17", P.margin_band(17), "p3")

check("full key", P.bucket_key(3, 7, 35, 4, 500, -5), "3|d7|C|q4|m1")
check("tier 1 drops the zone", P.coarser("3|d7|C|q4|m1", 1), "3|d7|q4|m1")
check("tier 2 drops distance", P.coarser("3|d7|C|q4|m1", 2), "3|q4|m1")
check("tier 3 drops margin", P.coarser("3|d7|C|q4|m1", 3), "3|q4")
check("tier 4 is down only", P.coarser("3|d7|C|q4|m1", 4), "3")


# ----------------------------------------------------------------- backoff
#
# A thin bucket must defer to the next coarser one, and a populated bucket
# must NOT be diluted by its neighbours.

counts = {
    "1|d10|B|h1|e": [400, 1000],     # 40%, plenty
    "3|d7|C|q4|m1": [30, 40],        # 75%, too thin on its own
    "3|d7|A|q4|m1": [60, 80],        # same tier-1 key, together 90/120
    "3|d7|D|q4|m1": [10, 50],        # and a run-heavy cousin: 100/170
}
B = P.Baseline(counts, [2030])
check("populated bucket is used as-is", B.expect("1|d10|B|h1|e"), (0.4, 0))
e, tier = B.expect("3|d7|C|q4|m1")
check("thin bucket falls back one tier", tier, 1)
check("fallback pools every zone", round(e, 4), round(100 / 170, 4))
e, tier = B.expect("4|d11|A|late|m3")
check("unknown key falls through to the league rate", tier, len(P.TIERS))
check("league rate is all plays", round(e, 4), round(500 / 1170, 4))
check("baseline play count", B.plays, 1170)
check("baseline seasons recorded", B.seasons, [2030])


# ------------------------------------------------------------------- plays


def row(team="AAA", opp="BBB", week="W1", qtr="1", down="1", dist="10", los="75",
        clock="12:00", margin="0", ptype="RUSH", desc="(12:00) 1-A.Back up the middle for 3 yards",
        scramble="0"):
    return {"team": team, "opponent": opp, "week": week, "qtr": qtr, "down": down,
            "dist": dist, "los": los, "GameClock": clock, "ScoreDiff": margin,
            "PlayType": ptype, "PlayDesc": desc, "Scramble?": scramble}


PRESENT = {"Scramble?"}
plays, dropped = P.plays_from_rows([
    row(ptype="PASS"),                                             # pass
    row(ptype="PASS", desc="(11:50) 1-A.QB sacked at AAA 20 for -5 yards"),   # sack: still a pass call
    row(ptype="RUSH", scramble="1"),                               # scramble: a pass call
    row(ptype="RUSH"),                                             # designed run
    row(ptype="RUSH", desc="(0:40) 1-A.QB kneels to AAA 30 for -1 yards"),    # kneel
    row(ptype="PASS", desc="(0:12) 1-A.QB spiked the ball to stop the clock"),  # spike
    row(ptype="PASS", down=""),                                    # two-point try, no down
    row(ptype="PASS", dist=""),                                    # missing distance
    row(ptype="FG"),                                               # not a scrimmage play
], PRESENT)
check("usable plays", len(plays), 4)
check("passes counted", sum(p["pass"] for p in plays), 3)
check("kneel and spike excluded", dropped["kneel or spike"], 2)
check("missing fields excluded", dropped["missing situation data"], 2)
check("non-scrimmage excluded", dropped["not a pass or run"], 1)
check("key carries the situation", plays[0]["key"], "1|d10|B|h1|e")

# Without the Scramble? column a scramble is a run — the pull warns, this just
# pins the behaviour.
plays2, _ = P.plays_from_rows([row(ptype="RUSH", scramble="1")], set())
check("scramble without the column reads as a run", plays2[0]["pass"], 0)

# Kneel pattern is the one shared by every tool.
check("dead-ball regex is the matchup tool's", P.DEAD_BALL_RE is pm.DEAD_BALL_RE, True)
check("kneeland is not a kneel", bool(P.DEAD_BALL_RE.search("tackled by 44-D.Kneeland")), False)


# ------------------------------------------------------------- team weeks
#
# Every play is credited once to the offense and once to the defense it faced,
# so a defense's cells are exactly the mirror of the offenses it played.

base = P.Baseline({"1|d10|B|h1|e": [500, 1000]}, [2030])   # expectation 0.5 everywhere
plays = []
for w in (1, 2):
    for _ in range(6):
        plays.append({"team": "AAA", "opp": "BBB", "week": w, "pass": 1, "key": "1|d10|B|h1|e"})
    for _ in range(4):
        plays.append({"team": "AAA", "opp": "BBB", "week": w, "pass": 0, "key": "1|d10|B|h1|e"})
    for _ in range(2):
        plays.append({"team": "BBB", "opp": "AAA", "week": w, "pass": 1, "key": "1|d10|B|h1|e"})
    for _ in range(8):
        plays.append({"team": "BBB", "opp": "AAA", "week": w, "pass": 0, "key": "1|d10|B|h1|e"})
tw, tiers = P.team_weeks(plays, base)
check("AAA offense week 1", tw["AAA"]["1"][:3], [6, 5.0, 10])
check("AAA defense week 1 mirrors BBB offense", tw["AAA"]["1"][3:6], [2, 5.0, 10])
check("BBB defense week 1 mirrors AAA offense", tw["BBB"]["1"][3:6], [6, 5.0, 10])
check("opponent recorded", tw["AAA"]["1"][6], "BBB")
check("every play resolved at tier 0", tiers, {0: 40})

check("PROE from cells", P.proe_of([tw["AAA"]["1"], tw["AAA"]["2"]], 0), (10.0, 20))
check("defense PROE against", P.proe_of([tw["AAA"]["1"]], 3), (-30.0, 10))
check("no plays gives None", P.proe_of([], 0), (None, 0))

# Last four reads the last four PLAYED weeks, skipping a bye.
six = {}
for i, w in enumerate((1, 2, 4, 5, 6, 7)):          # week 3 is the bye
    six[str(w)] = [10 if i < 2 else 5, 5.0, 10, 5, 5.0, 10, "BBB"]
summary = P.summarise({"CCC": six}, ["CCC"])
check("season PROE", summary["CCC"]["off"], round(100 * (40 - 30) / 60, 1))
check("last four skips the bye and the early weeks", summary["CCC"]["off_l4"], 0.0)
check("games counted", summary["CCC"]["games"], 6)
check("team with no plays", P.summarise({}, ["ZZZ"])["ZZZ"]["off"], None)


# ------------------------------------------------------------------- byes

teams = [f"T{i:02d}" for i in range(32)]


def week(w, missing=()):
    # Byes come in pairs: an odd number of teams cannot all play.
    pool = [t for t in teams if t not in missing]
    return [{"w": w, "away": pool[i], "home": pool[i + 1]} for i in range(0, len(pool) - 1, 2)]


sched = week(1) + week(2, missing=("T05", "T31")) + week(3, missing=("T09", "T12"))
byes = P.byes_from(sched, teams)
check("bye found", byes.get("T05"), 2)
check("its pair found", byes.get("T31"), 2)
check("second week found", byes.get("T09"), 3)
check("only the missing teams", sorted(byes), ["T05", "T09", "T12", "T31"])
# A week with only a handful of games published must not mark everyone absent.
byes2 = P.byes_from(sched + [{"w": 4, "away": "T00", "home": "T01"}], teams)
check("a half-published week is ignored", len(byes2), 4)
check("no schedule, no byes", P.byes_from(None, teams), {})


# ----------------------------------------------------------------- preload

names = {t: f"Team {t}" for t in ["AAA", "BBB"]}
html = P.preload_table(2030, {
    "AAA": {"off": 4.5, "off_l4": 6.0, "def": -1.0, "def_l4": None, "games": 4, "off_n": 1, "def_n": 1},
    "BBB": {"off": -2.0, "off_l4": -3.5, "def": 2.0, "def_l4": 1.0, "games": 4, "off_n": 1, "def_n": 1},
}, names)
check("preload ranks the pass-heavy offense first", html.index("Team AAA") < html.index("Team BBB"), True)
check("preload signs its figures", "+4.5" in html and "−2.0" not in html and "-2.0" in html, True)
check("preload dashes a missing figure", "—" in html, True)
check("preload header", '<th scope="col">Offense PROE</th>' in html, True)


# --------------------------------------------------------------- columns

for col in ("team", "opponent", "week", "qtr", "down", "dist", "los", "GameClock", "ScoreDiff", "PlayType", "PlayDesc"):
    check(f"{col} is required", col in P.REQUIRED_COLUMNS, True)
check("Scramble? is optional, not required", "Scramble?" in P.OPTIONAL_COLUMNS, True)


if failures:
    print("FAILED")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print(f"ok  test_proe: all checks passed")
