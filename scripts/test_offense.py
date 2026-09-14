#!/usr/bin/env python3
"""
Regression tests for scripts/offense.py — folding a play-logged-twice sheet
down to the offense's rows.

    python scripts/test_offense.py

No network, no data files. The fixture is one made-up game in the 2026 sheet's
shape: every play twice, team and opponent swapped, HomeRoad and ScoreDiff
flipped, with the traps that the real week 1 export set — an interception
whose yard line marks the turnover spot, a drive of nothing but incompletions,
a one-play drive by a player who appears nowhere else, and a blitz flag the
provider filled on the defense's copy only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import offense  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


HOME, AWAY = "HST", "BUF"       # provider codes; the module compares canonically


def play(pid, drive, off, desc, los, yds, **extra):
    """One play, returned as its two mirrored rows (offense first)."""
    deff = AWAY if off == HOME else HOME
    base = {
        "GameId": "g1", "PlayId": str(pid), "DriveNumber": str(drive),
        "PlayDesc": desc, "los": str(los), "yds": str(yds), "PlayType": "PASS",
        "PasserID": "", "RusherID": "", "TargetID": "", "Blitz?": "0",
        "PFFPrsrAlwd": "", "week": "W1", "qtr": "1", "down": "1",
    }
    base.update(extra)
    o = dict(base, team=off, opponent=deff, HomeRoad="Home" if off == HOME else "Road",
             ScoreDiff="3")
    d = dict(base, team=deff, opponent=off, HomeRoad="Road" if off == HOME else "Home",
             ScoreDiff="-3")
    return o, d


# Drive 1, Houston: two clean spots, one on each side of midfield.
D1 = [
    play(10, 1, HOME, "(15:00) 1-Q.Back pass short right to 2-R.Ceiver to HST 40 for 10 yards.",
         70, 10, PasserID="hqb", TargetID="hwr"),
    play(20, 1, HOME, "(14:20) 3-R.Unner up the middle to BUF 45 for 15 yards.",
         60, 15, RusherID="hrb"),
]
# Drive 2, Buffalo: the interception spot points the wrong way, but the drive
# shares its quarterback with drive 4, which carries clean votes.
D2 = [
    play(30, 2, AWAY, "(13:00) 9-J.Allen pass deep left INTERCEPTED by 5-J.Pitre at HST 20.",
         55, 0, PasserID="aqb", PlayResult="INT"),
]
# Drive 3, Houston: a blitz the provider logged on Buffalo's (defensive) copy.
D3 = [
    play(40, 3, HOME, "(12:00) (Shotgun) 1-Q.Back sacked at HST 30 for -8 yards.",
         62, -8, PasserID="hqb"),
]
D3[0][1]["Blitz?"] = "1"        # on the defense's row only, as in the real sheet
D3[0][1]["PFFPrsrAlwd"] = "Yes"
# Drive 4, Buffalo: nothing but incompletions — no spot to vote with — but the
# same passer as drive 2, so the cluster is named by ... nothing yet.
D4 = [
    play(50, 4, AWAY, "(11:00) 9-J.Allen pass incomplete short right to 14-S.Diggs.",
         75, 0, PasserID="aqb", TargetID="awr"),
    play(60, 4, AWAY, "(10:40) 9-J.Allen pass incomplete deep left to 14-S.Diggs.",
         75, 0, PasserID="aqb", TargetID="awr"),
]
# Drive 6, Buffalo: clean votes that name the Buffalo cluster (drives 2, 4, 6).
D6 = [
    play(70, 6, AWAY, "(9:00) 26-J.Cook left guard to BUF 30 for 5 yards.",
         75, 5, RusherID="arb", PasserID="aqb"),
    play(80, 6, AWAY, "(8:20) 9-J.Allen pass short middle to 14-S.Diggs to HST 45 for 25 yards.",
         70, 25, PasserID="aqb", TargetID="awr"),
]
# Drive 7, Houston: a lone spike by a player seen nowhere else and no yard line.
# Only alternation from drive 6 can place it. Drive 5 is deliberately missing
# (a kick-return drive with no scrimmage play), so parity has to use numbers.
D7 = [
    play(90, 7, HOME, "(:05) 12-B.Ackup spiked the ball to stop the clock.",
         40, 0, PasserID="hqb2"),
]

pairs = D1 + D2 + D3 + D4 + D6 + D7
rows = []
for o, d in pairs:
    rows += [d, o] if int(o["PlayId"]) % 20 == 0 else [o, d]   # mix the order up

kept, note = offense.offense_rows(rows)
check("one row per play", len(kept), len(pairs))
check("note is written", bool(note), True)
check("every kept row is the offense", [r["team"] for r in kept],
      [o["team"] for o, _ in pairs])
check("file order is preserved", [r["PlayId"] for r in kept],
      [o["PlayId"] for o, _ in pairs])
by_id = {r["PlayId"]: r for r in kept}
check("offense keeps its own score margin", by_id["10"]["ScoreDiff"], "3")
check("offense keeps its own home flag", by_id["70"]["HomeRoad"], "Road")
check("blitz flag merged from the defense's copy", by_id["40"]["Blitz?"], "1")
check("pressure-allowed flag merged too", by_id["40"]["PFFPrsrAlwd"], "Yes")
check("interception drive follows its quarterback", by_id["30"]["team"], AWAY)
check("incompletion drive follows its quarterback", by_id["50"]["team"], AWAY)
check("orphan spike placed by alternation", by_id["90"]["team"], HOME)
check("alternation is reported", "alternation" in note, True)


# ------------------------------------------------------------- the votes

check("spot on the offense's own side", offense.spot_vote(
    {"PlayDesc": "4-J.Cook left guard to BUF 43 for 9 yards.", "los": "66", "yds": "9"},
    "HOU", "BUF"), "BUF")
check("spot on the defense's side", offense.spot_vote(
    {"PlayDesc": "4-J.Cook up the middle to HST 43 for 11 yards.", "los": "54", "yds": "11"},
    "HOU", "BUF"), "BUF")
check("pushed out of bounds", offense.spot_vote(
    {"PlayDesc": "pass short right to 4-J.Cook pushed ob at BUF 46 for 3 yards.",
     "los": "57", "yds": "3"}, "HOU", "BUF"), "BUF")
check("midfield is no vote", offense.spot_vote(
    {"PlayDesc": "3-R.Unner up the middle to 50 for 5 yards.", "los": "55", "yds": "5"},
    "HOU", "BUF"), None)
check("a spot that does not add up is no vote", offense.spot_vote(
    {"PlayDesc": "pass short left to 14-S.Diggs to BUF 20 for 3 yards.", "los": "57", "yds": "3"},
    "HOU", "BUF"), None)
check("interceptions do not vote", offense.spot_vote(
    {"PlayDesc": "pass INTERCEPTED by 5-J.Pitre at HST 20.", "los": "80", "yds": "0"},
    "HOU", "BUF"), None)
check("penalties do not vote", offense.spot_vote(
    {"PlayDesc": "PENALTY on BUF-70-B.Guard, Holding, 10 yards, enforced at BUF 30 - No Play.",
     "los": "60", "yds": "0"}, "HOU", "BUF"), None)
check("jersey numbers are not team codes", offense.spot_vote(
    {"PlayDesc": "pass short right to 14-S.Diggs.", "los": "60", "yds": "0"},
    "HOU", "BUF"), None)
check("provider codes fold before comparing", offense.spot_vote(
    {"PlayDesc": "kneels to ARZ 26 for -1 yards.", "los": "73", "yds": "-1"},
    "ARI", "LAC"), "ARI")


# ------------------------------------------------- sheets that are not mirrored

single = [o for o, _ in pairs]
same, note = offense.offense_rows(single)
check("one-row-per-play sheet is returned as is", same is single, True)
check("and carries no note", note, None)

# The 2021-2024 sheets have no GameId or PlayId at all.
bare = [{k: v for k, v in r.items() if k not in ("GameId", "PlayId")} for r in rows]
same, note = offense.offense_rows(bare)
check("sheet without play ids is returned as is", same is bare, True)

# A play whose second copy is not a mirror (same team twice) is not a pair.
odd = [dict(rows[0]), dict(rows[0])]
same, _ = offense.offense_rows(odd)
check("duplicate rows are not a mirrored pair", same is odd, True)

# A single unpaired row in an otherwise mirrored sheet passes through.
extra = rows + [dict(pairs[0][0], PlayId="999", DriveNumber="9")]
kept, note = offense.offense_rows(extra)
check("unpaired row is kept", "999" in {r["PlayId"] for r in kept}, True)
check("unpaired row is reported", "1 unpaired" in note, True)

# A game with no usable description at all must fail loudly, not publish.
blind = []
for o, d in pairs:
    o, d = dict(o, PlayDesc="no yard line here"), dict(d, PlayDesc="no yard line here")
    blind += [o, d]
try:
    offense.offense_rows(blind)
    failures.append("a game with no evidence should raise")
except SystemExit as exc:
    check("failure names the game", "g1" in str(exc), True)


if failures:
    print(f"FAIL  {len(failures)} check(s) failed in test_offense.py")
    for f in failures:
        print("      x " + f)
    sys.exit(1)
print("ok    test_offense.py")
