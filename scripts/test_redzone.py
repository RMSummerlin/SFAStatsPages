#!/usr/bin/env python3
"""
Regression tests for pull_redzone.py.

    python scripts/test_redzone.py

No network and no data files. The workflow runs every scripts/test_*.py before
the pull step, so a failure here stops a bad build before it can commit data.

Each test exists because the obvious implementation is wrong in a way that
would not announce itself in the output: a band edge off by one moves goal
line carries into the wrong column, a kneel at the 1 reads as a carry, a
sack reads as a target, a nullified play keeps its target.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pull_redzone as R  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


# ------------------------------------------------------------------- bands

check("los 21 is outside", R.band_of(21), None)
check("los 20 is band 0", R.band_of(20), 0)
check("los 11 is band 0", R.band_of(11), 0)
check("los 10 is band 1", R.band_of(10), 1)
check("los 6 is band 1", R.band_of(6), 1)
check("los 5 is band 2", R.band_of(5), 2)
check("los 1 is band 2", R.band_of(1), 2)
check("los 0 is nothing", R.band_of(0), None)
check("no los", R.band_of(None), None)
check("zone 20 reads every band", R.bands_from(20), [0, 1, 2])
check("zone 10 reads the inner two", R.bands_from(10), [1, 2])
check("zone 5 reads the last", R.bands_from(5), [2])


# ----------------------------------------------------------------- fixture
#
# One game, KC at home against DEN, week 3, plus one DEN snap. Columns are
# the sheet's. Enough to exercise every rule in the docstring.

def row(team, opp, play_id, drive, los, dist, ptype, desc="", result="", yds="0",
        target="", tpos="", tname="", cmp_="", rusher="", rname="", passer="",
        pname="", scramble="0", drive_result="Punt", score="0", opp_score="0",
        epa="0", succ="0", week="W3"):
    return {
        "team": team, "opponent": opp, "week": week, "down": "1", "dist": dist,
        "los": los, "PlayType": ptype, "PlayDesc": desc, "PlayResult": result,
        "Yds": yds, "EPA": epa, "SuccessPlay": succ, "DriveNumber": drive,
        "DriveResult": drive_result, "TargetID": target, "TargetPos": tpos,
        "TargetName": tname, "Cmp": cmp_, "Scramble?": scramble, "RusherID": rusher,
        "RusherName": rname, "PasserID": passer, "PasserName": pname,
        "GameId": "g1", "PlayId": play_id, "TeamCurrentScore": score,
        "OppCurrentScore": opp_score,
    }


QB, RB, WR, TE, DB = "qb1", "rb1", "wr1", "te1", "db1"
ROWS = [
    # Drive 1: starts at the 45, reaches the red zone, scores through the air.
    row("KC", "DEN", "1", "1", "45", "10", "PASS", "pass to WR", "FIRST DOWN", "27",
        target=WR, tpos="WR", tname="Wide Out", cmp_="1", passer=QB, pname="Quarter Back",
        drive_result="Touchdown"),
    row("KC", "DEN", "2", "1", "18", "10", "RUSH", "RB up the middle", "", "7",
        rusher=RB, rname="Run Back", drive_result="Touchdown"),
    row("KC", "DEN", "3", "1", "11", "3", "PASS", "sacked", "SACK", "-6",
        passer=QB, pname="Quarter Back", drive_result="Touchdown"),
    row("KC", "DEN", "4", "1", "17", "9", "PASS", "pass incomplete to TE", "", "0",
        target=TE, tpos="TE", tname="Tight End", cmp_="0", passer=QB, pname="Quarter Back",
        drive_result="Touchdown"),
    row("KC", "DEN", "5", "1", "17", "9", "PASS", "pass to DB for 17 yards TOUCHDOWN", "TD", "17",
        target=DB, tpos="DB", tname="Two Way", cmp_="1", passer=QB, pname="Quarter Back",
        drive_result="Touchdown", epa="4.1", succ="1"),
    # The opponent's next snap carries KC's score after the try: 7, so the try
    # was good.
    row("DEN", "KC", "6", "1", "75", "10", "RUSH", "DEN run", "", "3",
        rusher="den_rb", rname="Den Back", score="0", opp_score="7"),
    # Drive 2: goal to go, a scramble, a kneel and a nullified pass, ends in a
    # field goal.
    row("KC", "DEN", "7", "2", "8", "8", "RUSH", "QB scrambles", "", "4",
        rusher=QB, rname="Quarter Back", scramble="1", drive_result="Field Goal",
        score="7"),
    row("KC", "DEN", "8", "2", "4", "4", "PASS",
        "pass incomplete to WR. PENALTY on KC-11-W.Out Offensive Pass Interference "
        "10 yards enforced at DEN 4.", "", "0",
        target=WR, tpos="WR", tname="Wide Out", cmp_="0", passer=QB, pname="Quarter Back",
        drive_result="Field Goal", score="7"),
    row("KC", "DEN", "9", "2", "14", "14", "RUSH", "QB kneels", "", "-1",
        rusher=QB, rname="Quarter Back", drive_result="Field Goal", score="7"),
    # Drive 3: a trip that ends in a lost fumble at the 3.
    row("KC", "DEN", "10", "3", "3", "3", "RUSH", "RB fumbles", "FUMBLE LOST", "0",
        rusher=RB, rname="Run Back", drive_result="Fumble", score="10", epa="-4.5"),
    # Drive 4: never reaches the 20. A target on it still counts as a game played.
    row("KC", "DEN", "11", "4", "60", "10", "PASS", "pass to TE", "FIRST DOWN", "12",
        target=TE, tpos="TE", tname="Tight End", cmp_="1", passer=QB, pname="Quarter Back",
        score="10"),
    # Drive 5: a kneel-out at the 15 is not a trip.
    row("KC", "DEN", "12", "5", "15", "10", "RUSH", "QB kneels", "", "-1",
        rusher=QB, rname="Quarter Back", drive_result="End of Game", score="10"),
    # A different week, so games played can be counted: RB carries at midfield.
    row("KC", "LV", "1", "1", "50", "10", "RUSH", "RB run", "", "4",
        rusher=RB, rname="Run Back", week="W4"),
]
PRESENT = set(R.OPTIONAL_COLUMNS)

plays, dropped = R.plays_from_rows(ROWS, PRESENT)
check("nullified pass dropped", dropped["nullified by penalty"], 1)
check("usable plays", len(plays), 12)

# A sack is a pass play with no target.
sack = [p for p in plays if p["order"] == 3][0]
check("sack carries no target", sack["target"], "")
check("sack is a dropback", sack["dropback"], True)
scr = [p for p in plays if p["order"] == 7][0]
check("scramble is a carry for the QB", scr["rusher"], QB)
check("scramble is a dropback", scr["dropback"], True)
check("goal to go flag", scr["g2g"], True)
check("not goal to go at the 17", [p for p in plays if p["order"] == 4][0]["g2g"], False)
check("kneel flagged", [p for p in plays if p["order"] == 9][0]["kneel"], True)

# ---------------------------------------------------------------- positions

pos = R.positions(plays)
check("passer is a QB", pos[QB], "QB")
check("untargeted rusher is a RB", pos[RB], "RB")
check("target tag wins", pos[TE], "TE")
check("DB target is a WR", pos[DB], "WR")

# ------------------------------------------------------------------ players

players, ptw = R.player_weeks(plays)
rb = players[RB]
check("RB games count the whole field", rb["g"], [3, 4])
check("RB latest team", rb["t"], "KC")
check("RB red zone weeks only", list(rb["w"]), ["3"])
cell = rb["w"]["3"]
check("RB week cell carries the team", cell[0], "KC")
check("RB carry at the 18 lands in band 0", cell[1][3], 1)
check("RB fumble at the 3 is a carry in band 2", cell[3][3], 1)
check("RB has no rushing TD", cell[1][4] + cell[2][4] + cell[3][4], 0)
check("RB has no targets", cell[1][0] + cell[2][0] + cell[3][0], 0)
qb = players[QB]
check("QB scramble is a band 1 carry", qb["w"]["3"][2][3], 1)
check("QB kneels are not carries", qb["w"]["3"][1][3] + qb["w"]["3"][3][3], 0)
check("QB is a QB", qb["p"], "QB")
check("WR nullified target not counted", WR in players, False)
te = players[TE]
check("TE incomplete target at the 17", te["w"]["3"][1][:3], [1, 0, 0])
check("TE games include the midfield catch", te["g"], [3])
two = players[DB]
check("two-way player is a WR", two["p"], "WR")
check("two-way TD in band 0", two["w"]["3"][1][:3], [1, 1, 1])
check("sack is nobody's target", sum(1 for p in players.values() if "3" in p["w"]), 4)

kc = ptw["KC"]["3"]
check("team cell opponent", kc[0], "DEN")
# Band 0: the RB run at the 18, the sack at the 11, the TE target at the 17,
# the TD at the 17. Four plays, three dropbacks, two targets, one carry, one TD.
check("team band 0 targets, carries, plays, dropbacks, TDs", kc[1], [2, 1, 4, 3, 1])
# Band 1: the scramble at the 8. Band 2: the fumble at the 3. Kneels excluded.
check("team band 1", kc[2], [0, 1, 1, 1, 0])
check("team band 2", kc[3], [0, 1, 1, 0, 0])
check("kneel-only week is not a team week", "3" in ptw.get("DEN", {}), False)

# ----------------------------------------------------------------- summary

s20 = R.player_summary(players, ptw, 20)
check("RB opportunities inside 20", s20[RB]["opp"], 2)
check("RB carry share: 2 of the team's 3 red zone carries", s20[RB]["car_share"], 2 / 3)
check("RB target share is 0 with no targets", s20[RB]["tg_share"], 0.0)
check("RB touchdown share: none of the team's one", s20[RB]["td_share"], 0.0)
check("two-way player's touchdown share", s20[DB]["td_share"], 1.0)
check("two-way player's target share: 1 of 2", s20[DB]["tg_share"], 0.5)
check("RB games", s20[RB]["games"], 2)
s5 = R.player_summary(players, ptw, 5)
check("inside the 5: RB fumble carry only", (s5[RB]["car"], s5[RB]["car_share"]), (1, 1.0))
check("inside the 5: QB nothing", s5[QB]["opp"], 0)
s_w4 = R.player_summary(players, ptw, 20, weeks={4})
check("week range: no red zone usage in week 4", s_w4[RB]["opp"], 0)
check("week range: games still count", s_w4[RB]["games"], 1)

# Shares are read against every game the team played, not the player's
# games, and a player who changed teams is read against each team for the
# weeks he was on it. Here the back carried twice for A in week 1 and once
# for B in week 3; A played weeks 1 and 2, B weeks 2, 3 and 4. Weeks 1 and 2
# count for A, 3 and 4 for B, so B's week 2 is not in his denominator.
Z = [0, 0, 0, 0, 0]
traded = {"x": {"n": "Moved Back", "p": "RB", "t": "B", "g": [1, 3],
               "w": {"1": ["A", [0, 0, 0, 2, 0], Z, Z], "3": ["B", [0, 0, 0, 1, 0], Z, Z]}}}
team_cells = {"A": {"1": ["Z", [0, 4, 4, 0, 1], Z, Z], "2": ["Z", [0, 4, 4, 0, 1], Z, Z]},
              "B": {"2": ["Z", [0, 10, 10, 0, 1], Z, Z], "3": ["Z", [0, 2, 2, 0, 1], Z, Z],
                    "4": ["Z", [0, 2, 2, 0, 1], Z, Z]}}
moved = R.player_summary(traded, team_cells, 20)["x"]
check("traded back: 3 of 12 carries", moved["car_share"], 0.25)
check("traded back: 0 of 4 touchdowns", moved["td_share"], 0.0)
check("team_at before his first week is his first team", R.team_at(traded["x"], 0), "A")
check("team_at between moves", R.team_at(traded["x"], 2), "A")
check("team_at after the move", R.team_at(traded["x"], 9), "B")
only_wk4 = R.player_summary(traded, team_cells, 20, weeks={4})["x"]
check("weeks filter: no carries, but a denominator", (only_wk4["car"], only_wk4["car_share"]), (0, 0.0))

# ------------------------------------------------------------------- teams

tw = R.team_weeks(plays, None)
kc3 = tw["KC"]["3"]
check("opponent", kc3[0], "DEN")
# Drives 1 (TD), 2 (FG), 3 (fumble) are trips; drive 4 never got there and
# drive 5 only knelt.
check("trips", kc3[1], 3)
check("touchdown trips", kc3[2], 1)
check("field goal trips", kc3[3], 1)
check("points: 6 plus the try read off the next snap, plus 3", kc3[4], 10)
check("red zone plays, kneels out", kc3[5], 6)
check("red zone dropbacks: sack, incomplete, TD, scramble", kc3[6], 4)
check("EPA", kc3[7], -0.4)
check("successes", kc3[8], 1)
check("giveaways", kc3[9], 1)
check("goal-to-go trips: drives 2 and 3", kc3[10], 2)
check("goal-to-go TDs", kc3[11], 0)
check("inside-10 trips: drives 2 and 3", kc3[12], 2)
check("inside-10 TDs", kc3[13], 0)
check("DEN never reached the red zone", "DEN" in tw, False)

# A touchdown drive that ends the game reads the try off the final score.
tail = [p for p in plays if p["order"] in (1, 2, 5)]
for p in tail:
    p["drive_result"] = "Touchdown"
end = R.team_weeks(tail, [{"w": 3, "away": "DEN", "home": "KC", "as": 3, "hs": 8}])
check("two-point try priced from the final score", end["KC"]["3"][4], 8)
end = R.team_weeks(tail, None)
check("no later snap and no schedule: assume 7", end["KC"]["3"][4], 7)

# ----------------------------------------------------------------- penalty

check("a standing play with a holding call beyond the line stays",
      R.negated_by_penalty(row("KC", "DEN", "1", "1", "40", "10", "RUSH",
                               "run for 8 yards. PENALTY on KC-71-O.Line Offensive Holding "
                               "10 yards enforced at DEN 38.", "", "2"), "KC"), False)
check("intentional grounding stays",
      R.negated_by_penalty(row("KC", "DEN", "1", "1", "40", "10", "PASS",
                               "pass incomplete. PENALTY on KC-15-Q.Back Intentional Grounding "
                               "13 yards enforced at DEN 40.", "", "0"), "KC"), False)
check("defensive holding from the previous spot on an incomplete pass goes",
      R.negated_by_penalty(row("KC", "DEN", "1", "1", "40", "10", "PASS",
                               "pass incomplete to WR. PENALTY on DEN-24-C.Back Defensive Holding "
                               "5 yards enforced at DEN 40.", "", "0"), "KC"), True)
check("a spot in the offense's own territory converts",
      R.negated_by_penalty(row("KC", "DEN", "1", "1", "70", "10", "PASS",
                               "pass incomplete to WR. PENALTY on KC-11-W.Out Offensive Pass "
                               "Interference 10 yards enforced at KC 30.", "", "0"), "KC"), True)
check("a dead-ball foul stays",
      R.negated_by_penalty(row("KC", "DEN", "1", "1", "40", "10", "PASS",
                               "pass incomplete. PENALTY on DEN-24-C.Back Taunting 15 yards "
                               "enforced at DEN 40.", "", "0"), "KC"), False)

# ------------------------------------------------------------------ report

if failures:
    print(f"{len(failures)} failure(s):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("test_redzone: all checks passed")
