#!/usr/bin/env python3
"""
Regression tests for scripts/pull_boxscore.py. Standard library, no network.

Pins the parts of the box score that are easy to break silently:
  * a turnover is INT, FUMBLE LOST or DEF TD; a recovered fumble is not
  * a kickoff or punt the receiving team fumbles or muffs to the kicking team
    is a turnover charged to the receiver, with the sign of its EPA flipped;
    one it gets back, one replay reverses, and a blocked kick are not, and
    the special teams rows add nothing to plays, drives or EPA
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
  * the quarter counters are the game line's arithmetic on a quarter's plays,
    a drive follows its starting quarter, overtime folds onto quarter 5, and
    the quarter file is sparse with the game count carried for averages
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
         "TeamCurrentScore": "0", "PlayId": "1", "PasserName": "QB " + team, "qtr": "1"}
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
    agg, _, _, _, n, excluded = pb.aggregate(rows, PRESENT)
    c = agg[("AAA", 1)]
    assert n == 7 and excluded == {"kneel or spike": 1}, (n, excluded)
    assert c["to"] == 3 and c["int"] == 2 and c["fum_lost"] == 1, dict(c)
    assert abs(c["to_epa"] - (-13.0)) < 1e-9
    assert c["fd"] == 2 and c["td"] == 1
    assert c["third"] == 3 and c["third_conv"] == 2
    assert c["explo"] == 3, "12-yard run, 15-yard pass and 25-yard pass are all explosive"
    print("ok  turnovers, first downs and third downs")


def test_special_teams_turnovers():
    # After offense.offense_rows() a kickoff is on the receiving team's row and
    # a punt on the punting team's. Descriptions are the 2026 gamebook shapes.
    rows = [
        row("AAA", "BBB", 1, "PASS", 0.1, 1, PlayId="1"),
        row("BBB", "AAA", 1, "RUSH", 0.2, 1, PlayId="2"),
        # AAA receives, fumbles, BBB recovers: AAA turnover. EPA is the kicker's view.
        row("AAA", "BBB", 1, "KICKOFF", 4.6, 0, yds=0, PlayId="3", DriveNumber="2",
            PlayDesc="4-K.Icker kicks 61 yards from BBB 35 to AAA 4. 9-K.Turpin to AAA 28 for 24 yards (29-M.Killebrew). FUMBLES (29-M.Killebrew) RECOVERED by BBB-38-K.Knowles at AAA 37."),
        # AAA punts, BBB muffs, AAA recovers: BBB turnover, credited to the opponent of the row.
        row("AAA", "BBB", 1, "PUNT", 5.2, 0, yds=0, PlayId="4", down="4",
            PlayDesc="(7:07) 19-T.Taylor punts 48 yards to BBB 22 Center-45-B.Gardner. 15-Ji.Horn MUFFS catch RECOVERED by AAA-81-K.Davis at BBB 28."),
        # Muffed and recovered by the receiving team: not a turnover.
        row("AAA", "BBB", 1, "PUNT", 1.3, 0, yds=0, PlayId="5", down="4",
            PlayDesc="(13:34) 19-D.Whelan punts 60 yards to BBB 8. 18-I.Williams MUFFS catch recovered by BBB-37-Q.Stiggers at BBB 2."),
        # Fumbled and recovered by the returner's own team, no "by": not a turnover.
        row("BBB", "AAA", 1, "KICKOFF", -0.3, 0, yds=0, PlayId="6",
            PlayDesc="18-E.Pineiro kicks 62 yards from AAA 35 to BBB 3. 88-J.Whittington to BBB 27 for 24 yards (33-S.Neal). FUMBLES (33-S.Neal) and recovers at BBB 27."),
        # Fumble recovered by the kicker, then overturned on replay: not a turnover.
        row("BBB", "AAA", 1, "KICKOFF", -0.6, 0, yds=0, PlayId="7",
            PlayDesc="8-R.Sanchez kicks 62 yards from AAA 35 to BBB 3. 11-T.Smith to BBB 32 for 29 yards. FUMBLES (55-C.Curry) RECOVERED by AAA-38-J.Owens at BBB 33. The Replay Official reviewed the runner was not down by contact ruling and the play was REVERSED. 8-R.Sanchez kicks 62 yards from AAA 35 to BBB 3. 11-T.Smith to BBB 32 for 29 yards."),
        # Blocked punt returned for a score: a change of possession, not a turnover.
        row("BBB", "AAA", 1, "PUNT", -5.6, 0, yds=0, PlayId="8", down="4", PlayResult="DEF TD",
            PlayDesc="(10:25) 8-R.Sanchez punt is BLOCKED by 36-J.Chestnut RECOVERED by AAA-7-O.Oladejo at BBB 14. 7-O.Oladejo for 14 yards TOUCHDOWN."),
        # Onside kick the kicking team recovers, on the kicker's own drive: no fumble, no turnover.
        row("AAA", "BBB", 1, "KICKOFF", -0.4, 0, yds=0, PlayId="9",
            PlayDesc="14-M.Gay kicks onside 20 yards from AAA 35 to BBB 45. 1-X.Worthy (didn't try to advance) to BBB 45 for no gain."),
        # Field goals, extra points and two-point tries are dropped outright.
        row("AAA", "BBB", 1, "FGA", 1.2, 0, yds=0, PlayId="10", PlayDesc="(7:32) 16-T.Bass 46 yard field goal is GOOD"),
        row("AAA", "BBB", 1, "XPA", 0.1, 0, yds=0, PlayId="11", PlayDesc="16-T.Bass extra point is GOOD"),
    ]
    agg, _, opp_of, _, n, excluded = pb.aggregate(rows, PRESENT)
    a, b = agg[("AAA", 1)], agg[("BBB", 1)]
    assert n == 2 and excluded == {"special teams": 9}, (n, excluded)
    assert a["to"] == 1 and a["fum_lost"] == 1 and a["st_to"] == 1 and a["int"] == 0, dict(a)
    assert b["to"] == 1 and b["fum_lost"] == 1 and b["st_to"] == 1, dict(b)
    assert abs(a["to_epa"] + 4.6) < 1e-9 and abs(b["to_epa"] + 5.2) < 1e-9, (a["to_epa"], b["to_epa"])
    # Nothing else moved: one scrimmage play, one drive, its EPA alone.
    assert a["plays"] == 1 and a["drives"] == 1 and abs(a["epa"] - 0.1) < 1e-9, dict(a)
    assert b["plays"] == 1 and b["drives"] == 1 and abs(b["epa"] - 0.2) < 1e-9, dict(b)
    assert opp_of[("AAA", 1)] == "BBB" and opp_of[("BBB", 1)] == "AAA"
    # A sheet without kick rows (2021-2025) has no special teams counter at all;
    # one with them publishes 0 for a team that lost nothing.
    agg2, _, _, _, _, _ = pb.aggregate(rows[:2], PRESENT)
    assert "st_to" not in agg2[("AAA", 1)] and agg2[("AAA", 1)]["to"] == 0
    rows3 = rows[:2] + [rows[8]]
    agg3, _, _, _, _, _ = pb.aggregate(rows3, PRESENT)
    assert agg3[("AAA", 1)]["st_to"] == 0 and agg3[("BBB", 1)]["st_to"] == 0
    # The provider's codes fold before comparing, and a kicker recovering on
    # the receiver's row is read from the description.
    assert pb.kick_turnover({"PlayDesc": "33-T.Loop kicks 61 yards from BLT 35 to IND 4. 20-S.McGowan to IND 30 for 26 yards. FUMBLES (48-C.Jones) RECOVERED by BLT-48-C.Jones at IND 30."},
                            "KICKOFF", "IND", "BAL") == "IND"
    assert pb.kick_turnover({"PlayDesc": "(:41) 12-B.Gillikin punts 46 yards to SF 30. 33-S.Neal MUFFS catch RECOVERED by ARZ-80-S.Fehoko at SF 28."},
                            "PUNT", "ARI", "SF") == "SF"
    print("ok  kickoff and punt turnovers charge the receiver and leave every other counter alone")


def test_zero_fill():
    rows = [row("AAA", "BBB", 1, "PASS", 0.1, 1)]
    agg, _, _, _, _, _ = pb.aggregate(rows, PRESENT)
    c = agg[("AAA", 1)]
    for k in ("to", "to_epa", "sack", "prsr", "blitz", "pa", "deep", "rz_trips", "fourth"):
        assert c[k] == 0, f"{k} should publish as 0"
    # Without the pressure column the counter is absent, so the tool shows a dash.
    agg2, _, _, _, _, _ = pb.aggregate(rows, PRESENT - {"PFFPrsrAlwd"})
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
    agg, _, _, _, _, _ = pb.aggregate(rows, PRESENT, {("AAA", 1): 24})
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
    agg, _, opp_of, passers, _, _ = pb.aggregate(rows, PRESENT)
    games, unmatched = pb.game_lines(agg, opp_of, passers, schedule())
    assert list(games) == ["S_01_AAA_BBB"]
    assert games["S_01_AAA_BBB"]["qb"] == {"AAA": "QB AAA", "BBB": "QB BBB"}
    assert len(unmatched) == 1 and "CCC" in unmatched[0], unmatched
    # The sheet disagreeing with the schedule on who played whom is not published.
    rows2 = [row("AAA", "CCC", 1, "PASS", 0.1, 1), row("BBB", "AAA", 1, "PASS", 0.2, 1)]
    agg, _, opp_of, passers, _, _ = pb.aggregate(rows2, PRESENT)
    games, unmatched = pb.game_lines(agg, opp_of, passers, schedule())
    assert not games and unmatched, unmatched
    print("ok  games publish only when both sides and the schedule agree")


def test_preload_and_totals():
    rows = [row("AAA", "BBB", 1, "PASS", 0.1, 1, yds=10), row("BBB", "AAA", 1, "RUSH", -0.2, 0, yds=2)]
    agg, _, opp_of, passers, _, _ = pb.aggregate(rows, PRESENT)
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


def test_quarters():
    rows = [
        # Q1: two plays, one explosive pass TD on a drive that starts in Q1 and
        # ends in Q2 (its clock and points stay in Q1).
        row("AAA", "BBB", 1, "PASS", 2.0, 1, yds=20, qtr="1", PlayId="1", DriveNumber="1",
            DriveResult="Touchdown", DriveStartClock="3:00", DriveEndClock="14:00", TeamCurrentScore="0", PlayResult="TD"),
        row("AAA", "BBB", 1, "RUSH", -0.5, 0, yds=2, qtr="2", PlayId="2", DriveNumber="1",
            DriveResult="Touchdown", DriveStartClock="3:00", DriveEndClock="14:00", TeamCurrentScore="0"),
        # Q3: an interception. Q4: nothing. OT (period 6 folds to 5): one run.
        row("AAA", "BBB", 1, "PASS", -4.0, 0, yds=0, qtr="3", PlayId="3", DriveNumber="2", PlayResult="INT",
            PlayDesc="pass INTERCEPTED by X", DriveStartClock="10:00", DriveEndClock="9:00", TeamCurrentScore="7"),
        row("AAA", "BBB", 1, "RUSH", 0.3, 1, yds=4, qtr="6", PlayId="4", DriveNumber="3",
            DriveStartClock="10:00", DriveEndClock="8:00", TeamCurrentScore="7"),
        row("BBB", "AAA", 1, "RUSH", 0.1, 1, yds=3, qtr="1", PlayId="5"),
        # A kickoff fumbled away in Q2 lands on the receiver's Q2 line.
        row("AAA", "BBB", 1, "KICKOFF", 4.6, 0, yds=0, qtr="2", PlayId="6", DriveNumber="4",
            PlayDesc="4-K.Icker kicks 61 yards from BBB 35 to AAA 4. 9-K.Turpin to AAA 28 for 24 yards. FUMBLES RECOVERED by BBB-38-K.Knowles at AAA 37."),
    ]
    agg, aggq, opp_of, passers, _, _ = pb.aggregate(rows, PRESENT, {("AAA", 1): 7})
    c = agg[("AAA", 1)]
    q1, q2, q3, q5 = (aggq[("AAA", 1, q)] for q in (1, 2, 3, 5))
    assert ("AAA", 1, 4) not in aggq, "no play in Q4 means no Q4 counter"
    # Plays split by quarter and sum to the game line.
    assert q1["plays"] == 1 and q2["plays"] == 1 and q3["plays"] == 1 and q5["plays"] == 1 and c["plays"] == 4
    assert q1["explo"] == 1 and q1["td"] == 1 and q1["pass_yds"] == 20
    assert q3["to"] == 1 and q3["int"] == 1 and abs(q3["to_epa"] + 4.0) < 1e-9
    assert sum(aggq[("AAA", 1, q)]["epa"] for q in (1, 2, 3, 5)) - c["epa"] < 1e-9
    # Drive 1 straddles Q1 and Q2: its count, points and clock sit in Q1 only.
    assert q1["drives"] == 1 and q1["drive_pts"] == 7 and q1["top"] == 240, dict(q1)
    assert "drives" not in q2 and "top" not in q2, dict(q2)
    assert q3["drives"] == 1 and q5["drives"] == 1 and c["drives"] == 3
    # The fumbled kickoff is a Q2 turnover with the kicker's EPA sign flipped.
    assert q2["to"] == 1 and q2["st_to"] == 1 and abs(q2["to_epa"] + 4.6) < 1e-9, dict(q2)
    assert c["to"] == 2
    # The quarter file is sparse, per game and per team, and carries games played.
    games, _ = pb.game_lines(agg, opp_of, passers, schedule())
    qg = pb.quarter_lines(aggq, games)
    line = qg["S_01_AAA_BBB"]["AAA"]
    assert sorted(line) == ["1", "2", "3", "5"], sorted(line)
    assert "sack" not in line["1"] and line["1"]["plays"] == 1
    assert qg["S_01_AAA_BBB"]["BBB"] == {"1": {"epa": 0.1, "plays": 1, "run": 1, "run_epa": 0.1, "run_succ": 1,
                                               "rush_plays": 1, "rush_yds": 3, "succ": 1, "yds": 3,
                                               "pers_n": 1, "p11": 1, "sg_n": 1, "shotgun": 1, "huddle_n": 1,
                                               "early": 1, "early_succ": 1, "ybc": 1, "ybc_n": 1,
                                               "yac_run": 2, "yac_n": 1, "drives": 1, "drive_start": 70,
                                               "start_n": 1, "top": 180, "top_n": 1}}, qg["S_01_AAA_BBB"]["BBB"]
    tot = pb.quarter_totals(qg, pb.season_totals(games, ["AAA", "BBB"]))
    assert tot["AAA"]["1"]["g"] == 1 and tot["AAA"]["1"]["plays"] == 1 and tot["AAA"]["5"]["g"] == 1
    assert list(tot["AAA"]) == ["1", "2", "3", "5"]
    # Without the column there are no quarter counters at all.
    agg2, aggq2, _, _, _, _ = pb.aggregate(rows, PRESENT - {"qtr"})
    assert not aggq2 and agg2[("AAA", 1)]["plays"] == 4
    print("ok  quarter counters split the game line and follow each drive's starting quarter")


def test_meetings():
    def game(gid, w, away, home, a, h):
        return {"id": gid, "w": w, "away": away, "home": home, "as": a, "hs": h}
    old = {"season": 2029, "games": {"a": {}, "b": {}, "c": {}},
           "schedule": [game("a", 3, "BBB", "AAA", 10, 7), game("b", 9, "AAA", "BBB", 21, 24),
                        game("c", 4, "AAA", "CCC", 3, 0), game("d", 12, "AAA", "BBB", None, None)]}
    new = {"season": 2030, "games": {"x": {}, "y": {}, "z": {}},
           "schedule": [game("x", 2, "AAA", "BBB", 20, 17), game("y", 5, "CCC", "DDD", 1, 0),
                        game("z", 14, "BBB", "AAA", 13, 6), game("u", 16, "AAA", "BBB", None, None)]}
    m = pb.meetings(new, pb.published_games(old))
    # Newest first, either side home, and this season's own earlier game counts.
    assert m["z"] == [[2030, 2, "AAA", "BBB", 20, 17], [2029, 9, "AAA", "BBB", 21, 24],
                      [2029, 3, "BBB", "AAA", 10, 7]], m["z"]
    assert m["x"] == [[2029, 9, "AAA", "BBB", 21, 24], [2029, 3, "BBB", "AAA", 10, 7]]
    # No earlier meeting, or a game not published, gets no entry; an unpublished
    # earlier game is never listed.
    assert "y" not in m and "u" not in m
    print("ok  meetings list earlier published games of the pair, newest first")


if __name__ == "__main__":
    test_turnovers_and_first_downs()
    test_special_teams_turnovers()
    test_zero_fill()
    test_drive_points_and_clock()
    test_game_matching()
    test_preload_and_totals()
    test_definitions()
    test_quarters()
    test_meetings()
    print("all boxscore tests passed")
