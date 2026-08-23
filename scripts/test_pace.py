#!/usr/bin/env python3
"""
Regression tests for pull_pace.py.

    python scripts/test_pace.py

No network and no data files, so it is safe to run anywhere. The workflow runs
every scripts/test_*.py before the pull step, so a failure here stops a bad
build before it can commit data.

Each test exists because the obvious implementation is wrong in a way that would
not announce itself in the output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pull_pace as P  # noqa: E402
from pull_personnel_grouping import DEAD_BALL_RE as PERSONNEL_DEAD_BALL  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


# --------------------------------------------------------------- drive clocks
#
# Drives that cross a quarter boundary have an end clock LARGER than their start
# clock, because both count down inside their own quarter. Subtracting naively
# gives a negative duration, which then quietly drags a team's time of possession
# down instead of raising an error.

check("same-quarter drive", P.drive_duration(900, 679), 221)
check("drive ending at 0:00", P.drive_duration(221, 0), 221)
# Q1 3:27 -> Q2 13:47, the real LAC drive this branch was written for.
check("drive crossing a quarter", P.drive_duration(207, 827), 280)
check("drive with no start clock", P.drive_duration(None, 500), None)
check("drive with no end clock", P.drive_duration(500, None), None)

# A drive cannot last longer than the quarter it crossed into.
for start, end in [(900, 0), (1, 899), (450, 450)]:
    seconds = P.drive_duration(start, end)
    if not 0 <= seconds <= 2 * P.QUARTER_SECONDS:
        failures.append(f"drive_duration({start}, {end}) = {seconds}, out of range")


# ---------------------------------------------------------------- clock parsing

check("clock mm:ss", P.parse_clock("12:46"), 766)
check("clock with no minutes", P.parse_clock(":08"), 8)
check("clock at zero", P.parse_clock("0:00"), 0)
check("clock full quarter", P.parse_clock("15:00"), 900)
check("clock with whitespace", P.parse_clock(" 3:05 "), 185)
check("clock that is blank", P.parse_clock(""), None)
check("clock that is not a clock", P.parse_clock("Q2"), None)
check("clock that is None", P.parse_clock(None), None)


# ------------------------------------------------------------ two-minute window
#
# The final two minutes of each HALF, not each quarter. Treating quarters 1 and 3
# as clock-strategy windows would throw away a chunk of ordinary neutral tempo.

check("end of Q2 is a two-minute window", P.in_last_two_minutes(2, 90), True)
check("end of Q4 is a two-minute window", P.in_last_two_minutes(4, 0), True)
check("exactly 2:00 counts", P.in_last_two_minutes(2, 120), True)
check("2:01 does not count", P.in_last_two_minutes(2, 121), False)
check("end of Q1 does not count", P.in_last_two_minutes(1, 30), False)
check("end of Q3 does not count", P.in_last_two_minutes(3, 30), False)
check("missing clock does not count", P.in_last_two_minutes(4, None), False)


# ------------------------------------------------------------------ week parsing

check("week W1", P.parse_week("W1"), 1)
check("week W18", P.parse_week("W18"), 18)
check("week lowercase", P.parse_week("w7"), 7)
check("week bare number", P.parse_week("7"), 7)
check("week blank", P.parse_week(""), None)


# ----------------------------------------------------------------- dead ball
#
# Kept in step with the personnel script on purpose. A plain substring test for
# "kneel" also swallows every play DE M. Kneeland is credited on, and the loss
# shows up only as a slightly larger excluded count.

check("dead-ball regex matches the personnel one",
      P.DEAD_BALL_RE.pattern, PERSONNEL_DEAD_BALL.pattern)

DEAD_BALL_CASES = [
    ("(:26) 17-J.Allen kneels to BUF 28 for -1 yards.", True),
    ("(1:02) 9-J.Burrow spiked the ball to stop the clock.", True),
    ("(3:14) 4-D.Prescott pass short right to 88-C.Lamb "
     "(56-M.Kneeland).", False),
    ("(8:00) 26-S.Barkley left end to NYG 30 for 4 yards "
     "(56-M.Kneeland; 91-O.Odighizuwa).", False),
]
for desc, want in DEAD_BALL_CASES:
    check(f"dead ball {desc[:34]!r}", bool(P.DEAD_BALL_RE.search(desc)), want)


# -------------------------------------------------------------------- encoding
#
# One character per play only works while every encoded value fits the alphabet.
# TimeSinceSnap is capped at 60 and 0 is the "no comparable gap" sentinel, so the
# cap has to stay below the alphabet size and above zero.

check("alphabet size", len(P.ALPHABET), 91)
check("alphabet has no backslash", "\\" in P.ALPHABET, False)
check("alphabet has no quote", '"' in P.ALPHABET, False)
check("alphabet is unique", len(set(P.ALPHABET)), len(P.ALPHABET))
if not 0 < P.TSS_CAP < P.BASE:
    failures.append(f"TSS_CAP {P.TSS_CAP} does not fit a single encoded character")
check("missing sentinel is zero", P.TSS_MISSING, 0)

# Margin is stored across two characters as margin + 100, so it has to survive a
# blowout in either direction.
for margin in (-90, -1, 0, 1, 90):
    shifted = margin + P.MARGIN_OFFSET
    if not 0 <= shifted < P.BASE * P.BASE:
        failures.append(f"margin {margin} does not encode")
    hi, lo = divmod(shifted, P.BASE)
    if hi * P.BASE + lo - P.MARGIN_OFFSET != margin:
        failures.append(f"margin {margin} does not round-trip")

# Drive durations are stored the same way and can exceed a single quarter.
for seconds in (0, 221, 721, P.BASE * P.BASE - 1):
    hi, lo = divmod(seconds, P.BASE)
    if hi * P.BASE + lo != seconds:
        failures.append(f"drive duration {seconds} does not round-trip")


# ------------------------------------------------------------- end-to-end build
#
# Two teams, one week, enough rows to exercise the sentinel, the cap, the neutral
# window and the drive table.

def row(**kw):
    base = {
        "team": "AAA", "opponent": "BBB", "week": "W1", "qtr": "1", "down": "1",
        "PlayType": "PASS", "PlayDesc": "(14:00) 1-A.Back pass short right.",
        "ScoreDiff": "0", "DriveNumber": "1", "TimeSinceSnap": "40",
        "Huddle": "Huddle", "HomeRoad": "Home", "GameClock": "14:00",
        "GameId": "1", "PlayId": "10", "DriveStartClock": "15:00",
        "DriveEndClock": "10:00", "DriveResult": "Punt",
    }
    base.update(kw)
    return base


rows = [
    row(PlayId="10", GameClock="15:00", TimeSinceSnap=""),        # sentinel
    row(PlayId="20", GameClock="14:20", TimeSinceSnap="40"),
    row(PlayId="30", GameClock="13:40", TimeSinceSnap="75"),      # winsorized
    row(PlayId="40", GameClock="13:00", TimeSinceSnap="30", Huddle="No-Huddle"),
    row(PlayId="50", qtr="2", GameClock="1:30", DriveNumber="2",
        DriveStartClock="2:10", DriveEndClock="0:00",
        DriveResult="End of Half"),                               # untimed drive
    row(PlayId="60", ScoreDiff="-21", qtr="3", GameClock="5:00",
        DriveNumber="3", DriveResult="Touchdown"),                # outside neutral
    row(PlayId="70", PlayDesc="(:30) 1-A.Back kneels to AAA 20.",
        DriveNumber="4"),                                          # excluded
    row(team="BBB", opponent="AAA", HomeRoad="Road", PlayId="80",
        DriveNumber="5", TimeSinceSnap="44"),
]

payload, summary = P.build_season(rows, 2025, set(P.OPTIONAL_COLUMNS))

check("plays kept", payload["plays"], 7)
check("kneel excluded", payload["excluded"].get("kneel or spike"), 1)
check("tempo detected", payload["has_tempo"], True)
check("drives detected", payload["has_drives"], True)
check("one play capped", payload["tss_capped"], 1)
check("teams found", payload["teams"], ["AAA", "BBB"])
check("every column is the same length",
      {len(v) for v in payload["cols"].values()}, {7})
check("every drive column is the same length",
      {len(v) for v in payload["dcols"].values()}, {payload["drives"]})

# The kneel was the only play on drive 4, so that drive should not exist at all.
check("drives kept", payload["drives"], 4)

decoded = [P.ALPHABET.index(ch) for ch in payload["cols"]["s"]]
check("blank TimeSinceSnap becomes the sentinel", decoded[0], P.TSS_MISSING)
check("75 seconds is winsorized to the cap", decoded[2], P.TSS_CAP)
check("no-huddle flag set", P.ALPHABET.index(payload["cols"]["n"][3]), 1)
check("home flag set for AAA", P.ALPHABET.index(payload["cols"]["hm"][0]), 1)
check("home flag clear for BBB", P.ALPHABET.index(payload["cols"]["hm"][-1]), 0)
check("two-minute flag set", P.ALPHABET.index(payload["cols"]["l2"][4]), 1)

# A season whose sheet predates the pace columns must still publish rather than
# raise, so that adding the column later is the only change needed.
bare = [{k: v for k, v in r.items() if k not in P.OPTIONAL_COLUMNS} for r in rows]
bare_payload, _ = P.build_season(bare, 2021, set())
check("season without tempo still builds", bare_payload["plays"], 7)
check("season without tempo is flagged", bare_payload["has_tempo"], False)
check("season without drives is flagged", bare_payload["has_drives"], False)
check("season without tempo has no drive rows", bare_payload["drives"], 0)


# ---------------------------------------------------------------------- report

if failures:
    print(f"FAIL  {len(failures)} check(s) failed in test_pace.py")
    for f in failures:
        print("      x " + f)
    sys.exit(1)
print("ok    test_pace.py")
