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
# Play clock used runs 1..40 with 0 as the "no comparable snap" sentinel, so the
# full clock has to stay below the alphabet size and above zero.

check("alphabet size", len(P.ALPHABET), 91)
check("alphabet has no backslash", "\\" in P.ALPHABET, False)
check("alphabet has no quote", '"' in P.ALPHABET, False)
check("alphabet is unique", len(set(P.ALPHABET)), len(P.ALPHABET))
if not 0 < P.PLAY_CLOCK < P.BASE:
    failures.append(f"PLAY_CLOCK {P.PLAY_CLOCK} does not fit a single encoded character")
check("missing sentinel is zero", P.TEMPO_MISSING, 0)

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
        "PlayClock": "5", "OffPenaltyYds": "", "DefPenaltyYds": "",
        "Huddle": "Huddle", "HomeRoad": "Home", "GameClock": "14:00",
        "GameId": "1", "PlayId": "10", "DriveStartClock": "15:00",
        "DriveEndClock": "10:00", "DriveResult": "Punt",
    }
    base.update(kw)
    return base


rows = [
    # No TimeSinceSnap: the play clock started at 25, so tempo is not comparable.
    row(PlayId="10", GameClock="15:00", TimeSinceSnap="", PlayClock="12"),
    row(PlayId="20", GameClock="14:20", PlayClock="5"),           # used 35
    row(PlayId="30", GameClock="13:40", PlayClock="0"),           # used the lot
    row(PlayId="40", GameClock="13:00", PlayClock="22", Huddle="No-Huddle"),
    row(PlayId="50", qtr="2", GameClock="1:30", DriveNumber="2",
        DriveStartClock="2:10", DriveEndClock="0:00",
        DriveResult="End of Half"),                               # untimed drive
    row(PlayId="60", ScoreDiff="-21", qtr="3", GameClock="5:00",
        DriveNumber="3", DriveResult="Touchdown"),                # outside neutral
    row(PlayId="70", PlayDesc="(:30) 1-A.Back kneels to AAA 20.",
        DriveNumber="4"),                                          # excluded
    row(team="BBB", opponent="AAA", HomeRoad="Road", PlayId="80",
        DriveNumber="5", PlayClock="9"),
]

P.mark_prior_penalties(rows, set(P.OPTIONAL_COLUMNS))
payload, summary = P.build_season(rows, 2025, set(P.OPTIONAL_COLUMNS))

check("plays kept", payload["plays"], 7)
check("kneel excluded", payload["excluded"].get("kneel or spike"), 1)
check("tempo detected", payload["has_tempo"], True)
check("drives detected", payload["has_drives"], True)
check("no play clock values out of range", payload["tempo_dropped"], 0)
check("teams found", payload["teams"], ["AAA", "BBB"])
check("every column is the same length",
      {len(v) for v in payload["cols"].values()}, {7})
check("every drive column is the same length",
      {len(v) for v in payload["dcols"].values()}, {payload["drives"]})

# The kneel was the only play on drive 4, so that drive should not exist at all.
check("drives kept", payload["drives"], 4)

decoded = [P.ALPHABET.index(ch) for ch in payload["cols"]["s"]]
check("a 25-second play clock is excluded from tempo", decoded[0], P.TEMPO_MISSING)
check("play clock at 5 means 35 used", decoded[1], 35)
check("play clock at 0 means the full 40 used", decoded[2], P.PLAY_CLOCK)
check("play clock at 22 means 18 used", decoded[3], 18)
check("no-huddle flag set", P.ALPHABET.index(payload["cols"]["n"][3]), 1)
check("home flag set for AAA", P.ALPHABET.index(payload["cols"]["hm"][0]), 1)
check("home flag clear for BBB", P.ALPHABET.index(payload["cols"]["hm"][-1]), 0)
check("two-minute flag set", P.ALPHABET.index(payload["cols"]["l2"][4]), 1)

# A season whose sheet predates the pace columns must still publish rather than
# raise, so that adding the column later is the only change needed.
bare = [{k: v for k, v in r.items()
         if k not in P.OPTIONAL_COLUMNS and not k.startswith("_")} for r in rows]
bare_payload, _ = P.build_season(bare, 2021, set())
check("season without tempo still builds", bare_payload["plays"], 7)
check("season without tempo is flagged", bare_payload["has_tempo"], False)
check("season without drives is flagged", bare_payload["has_drives"], False)
check("season without tempo has no drive rows", bare_payload["drives"], 0)


# ---------------------------------------------------------------- pass rate
#
# A dropback rate, not a PlayType rate. Sacks already arrive as PASS; scrambles
# arrive as RUSH despite the play call being a pass, and folding them back in
# moves teams by up to eleven rank positions, so the two definitions are not
# interchangeable.

pass_rows = [
    row(opponent="AAA", PlayId="10", PlayType="PASS"),
    row(opponent="AAA", PlayId="20", PlayType="RUSH"),
    row(opponent="AAA", PlayId="30", PlayType="RUSH", **{"Scramble?": "1"}),
    row(opponent="AAA", PlayId="40", PlayType="RUSH", **{"Scramble?": "TRUE"}),
    row(opponent="AAA", PlayId="50", PlayType="RUSH", **{"Scramble?": "0"}),
]
P.mark_prior_penalties(pass_rows, set(P.OPTIONAL_COLUMNS))
pass_payload, pass_summary = P.build_season(pass_rows, 2025, set(P.OPTIONAL_COLUMNS))
flags = [P.ALPHABET.index(ch) for ch in pass_payload["cols"]["p"]]
check("a pass counts as a pass", flags[0], 1)
check("a run does not", flags[1], 0)
check("a scramble flagged 1 counts as a pass", flags[2], 1)
check("a scramble flagged TRUE counts as a pass", flags[3], 1)
check("a scramble flagged 0 does not", flags[4], 0)
check("neutral pass rate is 3 of 5", pass_summary["team"]["AAA"]["passrate"], 60.0)

# Pass rate must not inherit the 40-second play clock gate — it has no need of
# one, and sharing the tempo denominator would quietly shrink it by a quarter.
gate_rows = [
    row(opponent="AAA", PlayId="10", PlayType="PASS", TimeSinceSnap=""),
    row(opponent="AAA", PlayId="20", PlayType="RUSH", TimeSinceSnap=""),
]
P.mark_prior_penalties(gate_rows, set(P.OPTIONAL_COLUMNS))
_, gate_summary = P.build_season(gate_rows, 2025, set(P.OPTIONAL_COLUMNS))
check("pass rate ignores the tempo gate",
      gate_summary["team"]["AAA"]["passrate"], 50.0)
check("tempo is still absent for those plays",
      gate_summary["team"]["AAA"]["sec"], None)


# ------------------------------------------------------------- team aliases
#
# Pooling seasons is by team code, so an unfolded rename shows up as a 33rd row
# rather than as an error. These pin the relocations and the alternate spellings.

for raw, want in [
    ("WFT", "WAS"), ("WSH", "WAS"), ("WAS", "WAS"),   # Football Team -> Commanders
    ("OAK", "LV"), ("LVR", "LV"), ("LV", "LV"),       # Oakland -> Las Vegas
    ("SD", "LAC"), ("SDG", "LAC"), ("LAC", "LAC"),    # San Diego -> Los Angeles
    ("STL", "LAR"), ("LA", "LAR"), ("LAR", "LAR"),    # St. Louis -> Los Angeles
    ("JAC", "JAX"), ("JAX", "JAX"),
    ("ARZ", "ARI"), ("BLT", "BAL"), ("CLV", "CLE"), ("HST", "HOU"),
    ("KAN", "KC"), ("NOR", "NO"), ("SFO", "SF"), ("GNB", "GB"), ("NWE", "NE"),
    ("TAM", "TB"),
    ("nyg", "NYG"), (" DAL ", "DAL"),                  # case and whitespace
]:
    check(f"team alias {raw!r}", P.canonical_team(raw), want)

check("unknown code passes through", P.canonical_team("XYZ"), "XYZ")
check("empty code stays empty", P.canonical_team(""), "")
check("None code stays empty", P.canonical_team(None), "")

# Every alias must resolve in one hop. A chain like A -> B -> C would leave rows
# under B, since canonical_team does a single lookup.
for src, dst in P.TEAM_ALIASES.items():
    if dst in P.TEAM_ALIASES and P.TEAM_ALIASES[dst] != dst:
        failures.append(f"alias {src} -> {dst} needs a second hop to "
                        f"{P.TEAM_ALIASES[dst]}")

# A season that spells Washington two ways must still produce one team.
alias_rows = [
    row(team="WFT", opponent="DAL", PlayId="10"),
    row(team="WAS", opponent="DAL", PlayId="20", week="W2"),
    row(team="DAL", opponent="WFT", PlayId="30"),
]
P.mark_prior_penalties(alias_rows, set(P.OPTIONAL_COLUMNS))
alias_payload, _ = P.build_season(alias_rows, 2021, set(P.OPTIONAL_COLUMNS))
check("renames pool into one team", alias_payload["teams"], ["DAL", "WAS"])
check("the fold is reported", alias_payload["renamed_teams"].get("WFT \u2192 WAS"), 2)


# ------------------------------------------------------- 25-second play clocks
#
# A snap after a penalty keeps its TimeSinceSnap but runs on a 25-second clock.
# Left in, it reads as an offence that burned 15 more seconds than it did. The
# real 2025 sheet has 260 of these and every one tops out at exactly 25.

pen_rows = [
    row(opponent="AAA", PlayId="10", PlayDesc="(9:00) 1-A.Back pass incomplete. "
        "PENALTY on AAA-70-B.Guard, Holding, 10 yards, enforced at AAA 30.",
        PlayClock="7"),
    row(opponent="AAA", PlayId="20", PlayClock="4"),   # 25-second clock, excluded
    row(opponent="AAA", PlayId="30", PlayClock="4"),   # back to a 40-second clock
]
P.mark_prior_penalties(pen_rows, set(P.OPTIONAL_COLUMNS))
check("penalty play itself is not flagged", pen_rows[0]["_prior_penalty"], False)
check("snap after a penalty is flagged", pen_rows[1]["_prior_penalty"], True)
check("the snap after that is not", pen_rows[2]["_prior_penalty"], False)

pen_payload, _ = P.build_season(pen_rows, 2025, set(P.OPTIONAL_COLUMNS))
pen_decoded = [P.ALPHABET.index(ch) for ch in pen_payload["cols"]["s"]]
check("post-penalty snap has no tempo", pen_decoded[1], P.TEMPO_MISSING)
check("the following snap does", pen_decoded[2], 36)

# The penalty column route and the description route should agree.
yard_rows = [
    row(opponent="AAA", PlayId="10", OffPenaltyYds="-10", PlayClock="7"),
    row(opponent="AAA", PlayId="20", PlayClock="4"),
]
P.mark_prior_penalties(yard_rows, set(P.OPTIONAL_COLUMNS))
check("penalty yardage also flags the next snap", yard_rows[1]["_prior_penalty"], True)


# ------------------------------------------------------------- play ordering
#
# The sheet groups plays by team, so the two offences in a game never interleave
# in file order. Sorting on PlayId is what makes "the previous play" mean
# anything. Rows below are deliberately out of file order.

mixed = [
    row(opponent="AAA", GameId="7", PlayId="30", PlayClock="4"),
    row(opponent="AAA", GameId="7", PlayId="10", PlayClock="7",
        PlayDesc="(9:00) PENALTY on AAA, Holding, 10 yards."),
    row(opponent="AAA", GameId="7", PlayId="20", PlayClock="4"),
]
P.mark_prior_penalties(mixed, set(P.OPTIONAL_COLUMNS))
check("PlayId ordering wins over file order",
      [r["_prior_penalty"] for r in mixed], [False, False, True])


# ---------------------------------------------------------------------- report

if failures:
    print(f"FAIL  {len(failures)} check(s) failed in test_pace.py")
    for f in failures:
        print("      x " + f)
    sys.exit(1)
print("ok    test_pace.py")
