#!/usr/bin/env python3
"""
Guard the shared team alias map.

A multi-season view must show 32 rows, not one row per name a franchise has worn.
The map lives in scripts/config.py so every pull_*.py folds history identically;
this checks the property that matters rather than the table's contents.

Run by the workflow before any pull. No network, no data files.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

failures = []
warnings = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


# The case that started this: the Rams are LA through 2024 and LAR from 2025.
check("LA folds to LAR", config.canonical_team("LA"), "LAR")
check("LAR is already canonical", config.canonical_team("LAR"), "LAR")
check("lowercase is handled", config.canonical_team("la"), "LAR")
check("surrounding space is handled", config.canonical_team("  LA "), "LAR")

# Unknown and empty input must pass through rather than raise or blank out.
check("unknown code passes through", config.canonical_team("XYZ"), "XYZ")
check("empty stays empty", config.canonical_team(""), "")
check("None stays empty", config.canonical_team(None), "")

# canonical_team does a single lookup, so a target must not itself be a key
# pointing somewhere else, or A -> B -> C would silently stop at B.
for src, dst in config.TEAM_ALIASES.items():
    if dst in config.TEAM_ALIASES and config.TEAM_ALIASES[dst] != dst:
        failures.append(
            f"alias chain: {src!r} -> {dst!r}, but {dst!r} -> "
            f"{config.TEAM_ALIASES[dst]!r}. Point {src!r} at the final code.")

# Every alias target should be a plausible current code.
for src, dst in config.TEAM_ALIASES.items():
    if not (2 <= len(dst) <= 3 and dst.isupper()):
        failures.append(f"alias target {dst!r} (from {src!r}) is not a team code")

# The published data must agree: no season may contain a code that still aliases.
data = Path(__file__).resolve().parent.parent / "data"
seen = set()
for path in sorted(data.glob("*_20??.json")):
    import json
    try:
        teams = json.loads(path.read_text(encoding="utf-8")).get("teams", [])
    except (json.JSONDecodeError, OSError):
        continue
    for t in teams:
        if config.canonical_team(t) != t:
            # A warning, not a failure. The workflow runs tests before the pull,
            # so failing here would block the very run that regenerates the data.
            warnings.append(
                f"{path.name} still contains {t!r}, which folds to "
                f"{config.canonical_team(t)!r}. Rebuild with the "
                f"'all_seasons' checkbox on a manual workflow run.")
        seen.add(config.canonical_team(t))

if seen and len(seen) != 32:
    warnings.append(f"published data covers {len(seen)} teams, expected 32: "
                    f"{sorted(seen)}")

for w in warnings:
    print("  ! " + w)
if failures:
    print(f"test_teams: {len(failures)} failure(s)")
    for f in failures:
        print("  x " + f)
    sys.exit(1)
print(f"test_teams: ok ({len(config.TEAM_ALIASES)} aliases, "
      f"{len(seen)} teams in data, {len(warnings)} warning(s))")
