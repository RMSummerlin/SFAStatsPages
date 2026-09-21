#!/usr/bin/env python3
"""
Work out what the sheet's `SuccessPlay` flag actually means, from the sheet.

Success rate is the one headline metric the pulls do not compute: `SuccessPlay`
arrives as a 0/1 flag and every tool just sums it. That makes the definition we
publish an assertion about someone else's data, so it needs checking against the
data rather than against memory. This script reads a season export and answers
three questions:

  1. What yardage does a play need, per down and distance, to be flagged? Read
     off the boundary between the longest flagged failure and the shortest
     flagged success at each distance.
  2. Which percentage reproduces every play? Scanned in 0.25% steps, printed as
     the widest band that misclassifies nothing.
  3. Does the vendor's own arithmetic agree? `AirYdsToSuccess` is the air yards
     a throw needed, so `AirYds - AirYdsToSuccess` is the yardage threshold
     stated by the sheet itself -- a second opinion that never touches the flag.

As of the 2025 export the answer is 45% of the distance on first down, 60% on
second and all of it on third and fourth, rounded to whole yards, never less
than one. See docs/metric-definitions.md.

Standard library only. The export is not in the repo, so pass one in.

Usage:
  python scripts/derive_success_rule.py path/to/season_export.csv
  python scripts/derive_success_rule.py export.csv --min-sample 40
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

# What we believe the flag means. The script's job is to try to break this.
PCT = {1: 0.45, 2: 0.60, 3: 1.00, 4: 1.00}
# A play cannot keep an offense on schedule without gaining a yard, so the
# rounded threshold has a floor: first-and-1 rounds to 0 yards without it.
MIN_YARDS = 1

REQUIRED = ["down", "dist", "Yds", "SuccessPlay"]


def as_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def half_up(x: float) -> int:
    """Round .5 away from zero. Python's round() goes to even, which would put
    first-and-10 at 4 yards instead of 5 and quietly change the answer."""
    return math.floor(x + 0.5)


def needed(down: int, dist: float, pct=PCT) -> int:
    return max(MIN_YARDS, half_up(pct[down] * dist))


def load(path: Path):
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"{path}: missing column(s) {', '.join(missing)}")
        rows = list(reader)
    plays = []
    for r in rows:
        down, dist, yds = r["down"], as_float(r["dist"]), as_float(r["Yds"])
        if down in ("1", "2", "3", "4") and dist and yds is not None and r["SuccessPlay"] in ("0", "1"):
            plays.append({
                "down": int(down), "dist": dist, "yds": yds, "succ": int(r["SuccessPlay"]),
                "result": (r.get("PlayResult") or "").strip().upper(),
                "desc": (r.get("PlayDesc") or "").strip(),
                "air": as_float(r.get("AirYds")), "air_succ": as_float(r.get("AirYdsToSuccess")),
            })
    return rows, plays


def thresholds(plays, min_sample):
    """The yardage boundary the flag draws at each down and distance."""
    print("\nWhere the flag turns over, by down and distance")
    print("  distance:shortest flagged success, and !=N where the rule expects N.")
    print("  A thin distance can miss its own boundary, so read the agreement below for the verdict.")
    by = defaultdict(lambda: {1: [], 0: []})
    for p in plays:
        by[(p["down"], int(p["dist"]))][p["succ"]].append(p["yds"])
    for down in (1, 2, 3, 4):
        cells = []
        for dist in sorted(d for dn, d in by if dn == down):
            s, f = by[(down, dist)][1], by[(down, dist)][0]
            if not s or not f or len(s) + len(f) < min_sample:
                continue
            obs, rule = int(min(s)), needed(down, dist)
            cells.append(f"{dist}:{obs}" + ("" if obs == rule else f"!={rule}"))
        print(f"  down {down} [{int(PCT[down] * 100)}%]  " + "  ".join(cells))


def agreement(plays):
    """How often each candidate percentage reproduces the flag."""
    print("\nHow well each candidate rule reproduces the flag")
    candidates = [
        ("45 / 60 / 100, rounded, min 1yd", PCT, True),
        ("45 / 60 / 100, rounded, no min", PCT, False),
        ("40 / 60 / 100, rounded, min 1yd", {1: 0.40, 2: 0.60, 3: 1.0, 4: 1.0}, True),
        ("50 / 60 / 100, rounded, min 1yd", {1: 0.50, 2: 0.60, 3: 1.0, 4: 1.0}, True),
    ]
    for label, pct, floor in candidates:
        miss = [p for p in plays
                if (1 if p["yds"] >= (max(MIN_YARDS, half_up(pct[p["down"]] * p["dist"])) if floor
                                      else half_up(pct[p["down"]] * p["dist"])) else 0) != p["succ"]]
        print(f"  {label:34s} {len(plays) - len(miss):6d}/{len(plays)} plays"
              f"  ({100 * (1 - len(miss) / len(plays)):7.3f}%)")
    miss = [p for p in plays if (1 if p["yds"] >= needed(p["down"], p["dist"]) else 0) != p["succ"]]
    print(f"\n  The {len(miss)} play(s) the published rule cannot explain:")
    for p in miss[:12]:
        print(f"    down {p['down']} and {int(p['dist'])}, gained {int(p['yds'])}, "
              f"flagged {p['succ']}, result {p['result'] or '(none)'}")
        print(f"      {p['desc'][:96]}")
    return miss


def bands(plays):
    """The widest percentage band per down that misclassifies nothing. A
    published figure outside its band is wrong, not a rounding choice."""
    print("\nEvery percentage that fits the flag exactly, by down")
    for down in (1, 2, 3, 4):
        sub = [p for p in plays if p["down"] == down and p["result"] != "TD"]
        fits = []
        step = 0.0025
        pct = 0.20
        while pct <= 1.30001:
            if not any((1 if p["yds"] >= max(MIN_YARDS, half_up(pct * p["dist"])) else 0) != p["succ"]
                       for p in sub):
                fits.append(pct)
            pct += step
        if fits:
            print(f"  down {down}: {len(sub):6d} plays   {min(fits) * 100:6.2f}% .. {max(fits) * 100:6.2f}%"
                  f"   (published {int(PCT[down] * 100)}%)")
        else:
            print(f"  down {down}: {len(sub):6d} plays   no percentage fits every play")


def vendor_check(plays, min_sample):
    """AirYds - AirYdsToSuccess is the sheet's own threshold, arrived at without
    reading the flag at all."""
    print("\nThe sheet's own threshold: AirYds - AirYdsToSuccess")
    obs = defaultdict(Counter)
    for p in plays:
        if p["air"] is not None and p["air_succ"] is not None:
            obs[(p["down"], int(p["dist"]))][int(p["air"] - p["air_succ"])] += 1
    agree = disagree = 0
    for down in (1, 2, 3, 4):
        cells = []
        for dist in sorted(d for dn, d in obs if dn == down):
            counts = obs[(down, dist)]
            if sum(counts.values()) < min_sample:
                continue
            mode = counts.most_common(1)[0][0]
            rule = needed(down, dist)
            cells.append(f"{dist}:{mode}" + ("" if mode == rule else f"!={rule}"))
            agree += mode == rule
            disagree += mode != rule
        print(f"  down {down} [{int(PCT[down] * 100)}%]  " + "  ".join(cells))
    print(f"\n  agrees with the rule at {agree} of {agree + disagree} down/distance pairs")


def turnovers(plays):
    """A turnover does not override the yardage, which surprises people."""
    tos = [p for p in plays if p["result"] in ("INTERCEPTION", "FUMBLE LOST")]
    flagged = [p for p in tos if p["succ"] == 1]
    print(f"\nTurnovers: {len(flagged)} of {len(tos)} interceptions and lost fumbles are "
          f"flagged a success,\n  because the flag reads yardage alone.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="a season export from the stats sheet")
    ap.add_argument("--min-sample", type=int, default=25,
                    help="ignore a down/distance with fewer plays than this (default 25)")
    args = ap.parse_args()
    if not args.csv.exists():
        sys.exit(f"{args.csv}: no such file")

    rows, plays = load(args.csv)
    print(f"{args.csv.name}: {len(rows)} rows, {len(plays)} with a down, distance, yardage and flag")
    thresholds(plays, args.min_sample)
    agreement(plays)
    bands(plays)
    vendor_check(plays, args.min_sample)
    turnovers(plays)


if __name__ == "__main__":
    main()
