#!/usr/bin/env python3
"""
Regression tests for scripts/pull_firsttd.py. Standard library, no network.

Pins the parts that are easy to break silently:
  * touchdowns are ordered by quarter and clock, not by row order, so the
    first is the first in time
  * a DEF TD is credited to the row's opponent; a kickoff, punt or blocked
    field goal return is read from the gamebook text and credited to the side
    that ended up with the ball; a nullified or reversed return is not one
  * extra point and two-point rows never score a touchdown
  * the scorer is the sheet's full name for an offensive touchdown and the
    gamebook's abbreviated name otherwise, resolved to a full name when the
    team's roster has exactly one match
  * the team table ranks by first touchdown rate over games played and the
    player table lists only players with a game's first touchdown
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pull_firsttd as pf  # noqa: E402

PRESENT = set(pf.OPTIONAL_COLUMNS)


def row(team, opp, week, ptype, qtr, clock, pid, result="", desc="pass short left", **extra):
    r = {"team": team, "opponent": opp, "week": f"W{week}", "PlayType": ptype, "PlayDesc": desc,
         "PlayResult": result, "qtr": str(qtr), "GameClock": clock, "PlayId": str(pid),
         "TargetName": "", "RusherName": "", "PasserName": "Quinn Back", "Scramble?": "0"}
    r.update(extra)
    return r


def game_rows():
    # Week 1, AAA at BBB. Rows deliberately out of time order.
    return [
        # Q2 AAA rushing TD (would be first by row order).
        row("AAA", "BBB", 1, "RUSH", 2, "9:00", 30, "TD", "22-R.Unner up the middle for 3 yards, TOUCHDOWN.",
            RusherName="Ray Unner"),
        # Q1 pick-six: AAA threw it, BBB scored. The game's first touchdown.
        row("AAA", "BBB", 1, "PASS", 1, "4:10", 20, "DEF TD",
            "(4:10) 9-Q.Back pass deep right INTERCEPTED by 5-J.Pitre at AAA 40. 5-J.Pitre for 40 yards, TOUCHDOWN."),
        # Q1 kickoff return TD by AAA (row is on the receiver's drive) - but
        # nullified, so not a touchdown.
        row("AAA", "BBB", 1, "KICKOFF", 1, "4:05", 21, "",
            "4-K.Icker kicks 65 yards from BBB 35 to AAA 0. 9-K.Turpin for 100 yards, TOUCHDOWN NULLIFIED by Penalty. PENALTY on AAA-55-X.Block, Illegal Block Above the Waist, 10 yards, enforced at AAA 30."),
        # Q3 punt muffed by BBB, AAA recovers and scores: AAA special teams TD.
        row("AAA", "BBB", 1, "PUNT", 3, "7:00", 40, "",
            "(7:00) 19-T.Taylor punts 48 yards to BBB 22. 15-Ji.Horn MUFFS catch RECOVERED by AAA-81-K.Davis at BBB 20. 81-K.Davis for 20 yards, TOUCHDOWN."),
        # Q3 passing TD by BBB to a receiver who is also the punt returner.
        row("BBB", "AAA", 1, "PASS", 3, "2:00", 45, "TD", "9-Q.Back pass short left to 15-Ji.Horn for 8 yards, TOUCHDOWN.",
            TargetName="Jim Horn"),
        # Q4 kickoff return TD reversed on replay, then re-run as a plain return.
        row("BBB", "AAA", 1, "KICKOFF", 4, "12:00", 50, "",
            "4-K.Icker kicks 65 yards from AAA 35 to BBB 0. 15-Ji.Horn for 100 yards, TOUCHDOWN. The Replay Official reviewed the play and it was REVERSED. 4-K.Icker kicks 65 yards from AAA 35 to BBB 0. 15-Ji.Horn to BBB 40 for 40 yards (33-S.Neal)."),
        # A two-point try returned by the defense is two points, not a touchdown.
        row("AAA", "BBB", 1, "TWOPOINTCONV", 4, "5:00", 60, "",
            "TWO-POINT CONVERSION ATTEMPT. 9-Q.Back pass is INTERCEPTED by 5-J.Pitre. 5-J.Pitre for 98 yards, TOUCHDOWN. ATTEMPT SUCCEEDS."),
        # Ordinary snaps, so both teams have the game and AAA has a roster.
        row("AAA", "BBB", 1, "PASS", 4, "3:00", 70, "", TargetName="Kai Davis"),
        row("BBB", "AAA", 1, "RUSH", 4, "2:00", 71, "", RusherName="Bo Back"),
    ]


def test_order_and_credit():
    tds, played, rosters, n, excluded = pf.touchdowns(game_rows(), PRESENT)
    assert n == 5 and excluded == {"special teams": 4}, (n, excluded)
    assert played == {"AAA": {1}, "BBB": {1}}
    assert rosters["AAA"] == {"Ray Unner", "Quinn Back", "Kai Davis"}, rosters["AAA"]
    seq = [(td["team"], td["kind"], td["scorer"], bool(td["text"])) for td in pf.by_game(tds)[(1, "AAA", "BBB")]]
    assert seq == [("BBB", "def", "J.Pitre", True), ("AAA", "off", "Ray Unner", False),
                   ("AAA", "st", "K.Davis", True), ("BBB", "off", "Jim Horn", False)], seq
    print("ok  touchdowns ordered by clock; DEF TD and kick returns credited to the right side")


def test_text_parsing():
    assert pf.text_scorer("5-J.Pitre at AAA 40. 5-J.Pitre for 40 yards, TOUCHDOWN.") == "J.Pitre"
    assert pf.text_scorer("pass to 14-A.St. Brown for 9 yards, TOUCHDOWN.") == "A.St. Brown"
    assert pf.text_scorer("to 11-J.Smith-Njigba for 60 yards, TOUCHDOWN.") == "J.Smith-Njigba"
    assert pf.text_scorer("to 14-S.Diggs. PENALTY on BBB, Holding. 22-R.Unner for 3 yards, TOUCHDOWN") == "R.Unner"
    assert pf.text_scorer("ran for 5 yards (33-S.Neal).") == ""
    # The forcer in parentheses is not the scorer; the recoverer after it is.
    assert pf.text_scorer("22-R.Unner FUMBLES (33-S.Neal), RECOVERED by AAA-77-O.Line at BBB 2. 77-O.Line for 2 yards, TOUCHDOWN.") == "O.Line"
    assert pf.text_scorer("22-R.Unner to BBB 1 for 9 yards (33-S.Neal). TOUCHDOWN") == "R.Unner"
    assert pf.text_touchdown("22-R.Unner for 3 yards, TOUCHDOWN.")
    assert not pf.text_touchdown("9-K.Turpin for 100 yards, TOUCHDOWN NULLIFIED by Penalty.")
    assert not pf.text_touchdown("9-K.Turpin for 100 yards, TOUCHDOWN. REVERSED. 9-K.Turpin to BBB 40 for 40 yards.")
    # Blocked field goal returned by the defense scores for the row's opponent.
    assert pf.kick_scorer_team("FGA", "16-T.Bass 46 yard field goal is BLOCKED RECOVERED by BBB-7-O.Oladejo. 7-O.Oladejo for 60 yards, TOUCHDOWN.",
                               "AAA", "BBB") == "BBB"
    # A kickoff returned all the way scores for the receiver, the row's team.
    assert pf.kick_scorer_team("KICKOFF", "kicks 65 yards. 9-K.Turpin for 100 yards, TOUCHDOWN.", "AAA", "BBB") == "AAA"
    # The provider's codes fold before comparing.
    assert pf.kick_scorer_team("PUNT", "MUFFS catch RECOVERED by HST-81-K.Davis. TOUCHDOWN.", "ARI", "HOU") == "HOU"
    assert pf.resolve_name("J.Pitre", {"Jalen Pitre", "Jalen Hurts"}) == "Jalen Pitre"
    assert pf.resolve_name("J.Pitre", {"Jalen Pitre", "Jack Pitre"}) == "J.Pitre"
    assert pf.resolve_name("A.St. Brown", {"Amon-Ra St. Brown"}) == "Amon-Ra St. Brown"
    assert pf.resolve_name("M.Harrison", {"Marvin Harrison Jr."}) == "Marvin Harrison Jr."
    assert pf.resolve_name("Ji.Horn", {"Jim Horn", "Jack Horn"}) == "Jim Horn"
    print("ok  gamebook names, nullified and reversed touchdowns, recoveries")


def test_tables():
    rows = game_rows()
    # Week 2: AAA at CCC, no touchdowns at all; CCC also plays week 3 and
    # scores first there with the same receiver twice.
    rows += [row("AAA", "CCC", 2, "PASS", 1, "10:00", 1, ""), row("CCC", "AAA", 2, "RUSH", 1, "9:00", 2, "")]
    rows += [row("CCC", "DDD", 3, "PASS", 2, "10:00", 1, "TD", TargetName="Will Out"),
             row("CCC", "DDD", 3, "PASS", 4, "1:00", 9, "TD", TargetName="Will Out"),
             row("DDD", "CCC", 3, "RUSH", 3, "9:00", 5, "TD", RusherName="Dee Back")]
    tds, played, rosters, _, _ = pf.touchdowns(rows, PRESENT)
    teams, players = pf.summarise(tds, played, rosters)
    assert teams["AAA"] == {"g": 2, "first": 0, "td": 2, "off": 1}, teams["AAA"]
    assert teams["BBB"] == {"g": 1, "first": 1, "td": 2, "off": 1}, teams["BBB"]
    assert teams["CCC"] == {"g": 2, "first": 1, "td": 2, "off": 2}, teams["CCC"]
    assert teams["DDD"] == {"g": 1, "first": 0, "td": 1, "off": 1}, teams["DDD"]
    # K.Davis resolves to the roster's Kai Davis; J.Pitre has no offensive
    # snap on BBB and stays abbreviated.
    assert players[("AAA", "Kai Davis")] == {"first": 0, "first_team": 0, "td": 1}
    assert players[("BBB", "J.Pitre")] == {"first": 1, "first_team": 1, "td": 1}
    assert players[("AAA", "Ray Unner")] == {"first": 0, "first_team": 1, "td": 1}
    assert players[("CCC", "Will Out")] == {"first": 1, "first_team": 1, "td": 2}
    assert players[("DDD", "Dee Back")] == {"first": 0, "first_team": 1, "td": 1}
    names = {t: "Team " + t for t in teams}
    html = pf.team_preload(2030, teams, names, 3)
    order = [seg.split("</th>")[0] for seg in html.split('<th scope="row">')[1:]]
    assert order == ["Team BBB", "Team CCC", "Team AAA", "Team DDD"], order
    assert "<td>2</td><td>1</td><td>50%</td><td>2</td><td>2</td>" in html, html
    assert "through Week 3" in html
    html = pf.player_preload(2030, players, 3)
    names_in = [seg.split("</th>")[0] for seg in html.split('<th scope="row">')[1:]]
    assert names_in == ["Will Out (CCC)", "J.Pitre (BBB)"], names_in
    assert "<td>1</td><td>1</td><td>2</td>" in html
    print("ok  team rate over games played, player table limited to game firsts")


def test_no_clock_columns():
    # Without qtr and clock the order is PlayId, so the first row wins here.
    rows = [r for r in game_rows()]
    for r in rows:
        r.pop("qtr"); r.pop("GameClock")
    tds, _, _, _, _ = pf.touchdowns(rows, PRESENT - {"qtr", "GameClock"})
    first = pf.by_game(tds)[(1, "AAA", "BBB")][0]
    assert first["kind"] == "def" and first["qtr"] is None, first
    print("ok  PlayId orders the touchdowns when there is no clock")


if __name__ == "__main__":
    test_order_and_credit()
    test_text_parsing()
    test_tables()
    test_no_clock_columns()
    print("all firsttd tests passed")
