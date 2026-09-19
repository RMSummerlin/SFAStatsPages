#!/usr/bin/env python3
"""
Regression tests for scripts/pull_boxscore.py. Standard library, no network.

Pins the parts of the box score that are easy to break silently:
  * a turnover is INT, FUMBLE LOST or DEF TD; a recovered fumble is not
  * first downs count FIRST DOWN and TD results, and a third down converts
    on either
  * counters whose column exists publish as 0, not as a gap
  * drive points read the score before and after the drive, so a missed
    extra point is 6 and a two-point try is 8, with the final score pricing
    the last drive
  * possession time crosses the quarter boundary correctly
  * a game is published only when both teams' rows agree on the opponent and
    the schedule has the game
  * the better side of a stat is decided by hi_good, and the preload table
    carries one row per team-game with its game class
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pull_boxscore as pb  # noqa: E402

PRESENT = set(pb.OPTIONAL_COLUMNS)


def row(team, opp, week, ptype, epa, succ, yds=3, **extra):
    r = {"team": team, "opponent": opp, "week": f"W{week}", "down": "1", "dist": "10",
         "PlayType": ptype, "PlayDesc": "pass short left", "EPA": str(epa), "SuccessPlay": str(succ),
         "Yds": str(yds), "PlayResult": "", "Scramble?": "0", "Sacked": "", "PFFPrsrAlwd": "",
         "Blitz?": "0", "PFFCoverageType": "3", "PlayAct": "", "AirYds": "5", "Att": "1", "Cmp": "1",
         "TTT": "2.5s", "YdsPreCt": "1", "YdsPostCt": "2", "OffPers": "11", "Shotgun": "Yes",
         "Huddle": "Huddle", "los": "60", "DriveNumber": "1", "DriveResult": "Punt",
         "DriveStartClock": "15:00", "DriveEndClock": "12:00", "DriveStartDist": "70",
         "TeamCurrentScore": "0", "PlayId": "1", "PasserName": "QB " + team}
    r.update(extra)
    return r


def schedule():
    return [{"id": "S_01_AAA_BBB", "w": 1, "date": "2030-01-01", "time": "13:00", "day": "Sun",
             "away": "AAA", "home": "BBB", "neutral": False, "stadium": "",
             "as": 20, "hs": 17, "aqb": "", "hqb": "", "acoach": "", "hcoach": ""}]


def test_turnovers_and_first_downs():
    rows = [
        row("AAA", "BBB", 1, "PASS", -4.0, 0, yds=0, PlayResult="INT", PlayDesc="pass INTERCEPTED by X", PlayId="1"),
        row("AAA", "BBB", 1, "RUSH", -3.0, 0, yds=2, PlayResult="FUMBLE LOST", PlayDesc="run FUMBLES, recovered by BBB", PlayId="2"),
        row("AAA", "BBB", 1, "PASS", -6.0, 0, yds=0, PlayResult="DEF TD", PlayDesc="pass INTERCEPTED by Y for TOUCHDOWN", PlayId="3"),
        row("AAA", "BBB", 1, "RUSH", 0.5, 1, yds=12, PlayResult="FUMBLE", PlayDesc="run FUMBLES, recovered by AAA", PlayId="4"),
        row("AAA", "BBB", 1, "PASS", 2.0, 1, yds=15, PlayResult="FIRST DOWN", down="3", dist="7", PlayId="5"),
        row("AAA", "BBB", 1, "PASS", 4.0, 1, yds=25, PlayResult="TD", down="3", dist="7", PlayId="6"),
        row("AAA", "BBB", 1, "RUSH", -0.5, 0, yds=2, down="3", dist="7", PlayId="7"),
        row("AAA", "BBB", 1, "RUSH", -1.0, 0, yds=-1, PlayDesc="QB kneels", PlayId="8"),
    ]
    agg, _, _, n, excluded = pb.aggregate(rows, PRESENT)
    c = agg[("AAA", 1)]
    assert n == 7 and excluded == {"kneel or spike": 1}, (n, excluded)
    assert c["to"] == 3 and c["int"] == 2 and c["fum_lost"] == 1, dict(c)
    assert abs(c["to_epa"] - (-13.0)) < 1e-9
    assert c["fd"] == 2 and c["td"] == 1
    assert c["third"] == 3 and c["third_conv"] == 2
    assert c["explo"] == 3, "12-yard run, 15-yard pass and 25-yard pass are all explosive"
    print("ok  turnovers, first downs and third downs")


def test_zero_fill():
    rows = [row("AAA", "BBB", 1, "PASS", 0.1, 1)]
    agg, _, _, _, _ = pb.aggregate(rows, PRESENT)
    c = agg[("AAA", 1)]
    for k in ("to", "to_epa", "sack", "prsr", "blitz", "pa", "deep", "rz_trips", "fourth"):
        assert c[k] == 0, f"{k} should publish as 0"
    # Without the pressure column the counter is absent, so the tool shows a dash.
    agg2, _, _, _, _ = pb.aggregate(rows, PRESENT - {"PFFPrsrAlwd"})
    assert "prsr" not in agg2[("AAA", 1)]
    assert pb.fmt(pb.STAT_BY_KEY["prsr"], agg2[("AAA", 1)]) == "–"
    print("ok  counters publish as 0 when their column exists, and as a gap when it does not")


def test_drive_points_and_clock():
    rows = [
        # Drive 1: TD, extra point missed (next drive starts at 6).
        row("AAA", "BBB", 1, "RUSH", 1.0, 1, DriveNumber="1", DriveResult="Touchdown", TeamCurrentScore="0",
            DriveStartClock="14:00", DriveEndClock="10:00", DriveStartDist="75", PlayId="1", PlayResult="TD"),
        # Drive 2: field goal.
        row("AAA", "BBB", 1, "RUSH", 0.2, 1, DriveNumber="2", DriveResult="Field Goal", TeamCurrentScore="6",
            DriveStartClock="3:00", DriveEndClock="14:00", DriveStartDist="50", PlayId="2", los="15"),
        # Drive 3: TD with a two-point conversion (next drive starts at 17).
        row("AAA", "BBB", 1, "PASS", 3.0, 1, DriveNumber="3", DriveResult="Touchdown", TeamCurrentScore="9",
            DriveStartClock="8:00", DriveEndClock="6:00", DriveStartDist="65", PlayId="3", los="10", PlayResult="TD"),
        # Drive 4: last drive, TD, priced by the final score of 24.
        row("AAA", "BBB", 1, "PASS", 3.0, 1, DriveNumber="4", DriveResult="Touchdown", TeamCurrentScore="17",
            DriveStartClock="2:00", DriveEndClock="0:30", DriveStartDist="60", PlayId="4", PlayResult="TD"),
    ]
    agg, _, _, _, _ = pb.aggregate(rows, PRESENT, {("AAA", 1): 24})
    c = agg[("AAA", 1)]
    assert c["drives"] == 4
    assert c["drive_pts"] == 6 + 3 + 8 + 7, c["drive_pts"]
    # 4:00 + (3:00 + 1:00 across the quarter break) + 2:00 + 1:30 = 11:30
    assert c["top"] == 240 + 240 + 120 + 90, c["top"]
    assert c["drive_start"] == 250 and c["start_n"] == 4
    assert c["rz_trips"] == 2 and c["rz_td"] == 1, (c["rz_trips"], c["rz_td"])
    assert pb.fmt(pb.STAT_BY_KEY["top"], c) == "11:30"
    assert pb.fmt(pb.STAT_BY_KEY["start"], c) == "Own 38"
    print("ok  drive points read the score, possession crosses the quarter, red zone trips count")


def test_game_matching():
    rows = [row("AAA", "BBB", 1, "PASS", 0.1, 1), row("BBB", "AAA", 1, "PASS", 0.2, 1),
            row("CCC", "DDD", 1, "PASS", 0.3, 1)]
    agg, opp_of, passers, _, _ = pb.aggregate(rows, PRESENT)
    games, unmatched = pb.game_lines(agg, opp_of, passers, schedule())
    assert list(games) == ["S_01_AAA_BBB"]
    assert games["S_01_AAA_BBB"]["qb"] == {"AAA": "QB AAA", "BBB": "QB BBB"}
    assert len(unmatched) == 1 and "CCC" in unmatched[0], unmatched
    # The sheet disagreeing with the schedule on who played whom is not published.
    rows2 = [row("AAA", "CCC", 1, "PASS", 0.1, 1), row("BBB", "AAA", 1, "PASS", 0.2, 1)]
    agg, opp_of, passers, _, _ = pb.aggregate(rows2, PRESENT)
    games, unmatched = pb.game_lines(agg, opp_of, passers, schedule())
    assert not games and unmatched, unmatched
    print("ok  games publish only when both sides and the schedule agree")


def test_preload_and_totals():
    rows = [row("AAA", "BBB", 1, "PASS", 0.1, 1, yds=10), row("BBB", "AAA", 1, "RUSH", -0.2, 0, yds=2)]
    agg, opp_of, passers, _, _ = pb.aggregate(rows, PRESENT)
    games, _ = pb.game_lines(agg, opp_of, passers, schedule())
    html = pb.preload_table(2030, 1, schedule(), games, {"AAA": "Team A", "BBB": "Team B"})
    assert html.count('<tr class="g-aaa-bbb">') == 2
    assert "W 20-17" in html and "L 17-20" in html
    assert "at Team B" in html and "vs Team A" in html
    tot = pb.season_totals(games, ["AAA", "BBB"])
    assert tot["AAA"]["g"] == 1 and tot["AAA"]["yds"] == 10
    league = pb.league_totals(games)
    assert league["g"] == 2 and league["yds"] == 12
    print("ok  preload rows carry the game class and result; totals sum per team and league")


def test_definitions():
    keys = [s["key"] for s in pb.STATS]
    assert len(keys) == len(set(keys)), "duplicate stat key"
    for h in pb.HEADER:
        assert h["key"] in pb.STAT_BY_KEY, h
        assert pb.STAT_BY_KEY[h["key"]]["hi_good"] is not None, "a header bar needs a better side"
        assert h["scale"] > 0
    for k in pb.PRELOAD_KEYS:
        assert k in pb.STAT_BY_KEY
    groups = {g["key"] for g in pb.GROUPS}
    assert all(s["group"] in groups for s in pb.STATS)
    print("ok  stat, header and preload definitions agree")


if __name__ == "__main__":
    test_turnovers_and_first_downs()
    test_zero_fill()
    test_drive_points_and_clock()
    test_game_matching()
    test_preload_and_totals()
    test_definitions()
    print("all boxscore tests passed")
