#!/usr/bin/env python3
"""
Regression test for the kneel/spike exclusion in pull_personnel_grouping.py.

    python scripts/test_dead_ball.py

No network and no data files, so it is safe to run anywhere.

This exists because the obvious implementation is wrong in a way that hides
itself: matching "kneel" as a substring also swallows every play DE M. Kneeland
is credited on, and the loss shows up only as a slightly larger "kneel or spike"
count in the excluded totals. PlayDesc carries player surnames, so any future
matcher on that column needs the same care.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pull_personnel_grouping import DEAD_BALL_RE  # noqa: E402

CASES = [
    # (PlayDesc, should be excluded)
    ("(:26) 17-J.Allen kneels to BUF 28 for -1 yards.", True),
    ("(1:12) 11-M.Trubisky kneels to BUF 21 for -1 yards.", True),
    ("(1:00) 16-J.Goff kneels to MIN 26 for -1 yards.", True),
    ("(:22) (No Huddle) 17-J.Allen spiked the ball to stop the clock.", True),
    ("(:04) (No Huddle) 5-A.Richardson spiked the ball to stop the clock.", True),
    # M. Kneeland is a player, not a kneel-down. All three are real plays.
    ("(4:24) 7-B.Irving right tackle to DAL 46 for no gain (2-J.Lewis; 94-M.Kneeland).", False),
    ("(12:56) 34-J.Ford right tackle to CLV 24 for 1 yard (94-M.Kneeland).", False),
    ("(11:09) (Shotgun) 2-J.Fields left end to PIT 42 for 5 yards (94-M.Kneeland).", False),
    # Ordinary plays and empty cells.
    ("(8:31) (Shotgun) 15-P.Mahomes pass short right to 87-T.Kelce for 9 yards.", False),
    ("", False),
    (None, False),
]


def is_dead_ball(desc):
    return bool(DEAD_BALL_RE.search(desc or ""))


failures = [
    f"{desc!r}\n      got {is_dead_ball(desc)}, wanted {want}"
    for desc, want in CASES
    if is_dead_ball(desc) != want
]

if failures:
    print(f"FAIL — {len(failures)} of {len(CASES)} cases:")
    for line in failures:
        print("  -", line)
    sys.exit(1)

print(f"dead-ball matcher: {len(CASES)} cases passed")
