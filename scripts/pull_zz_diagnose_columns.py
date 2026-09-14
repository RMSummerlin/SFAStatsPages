#!/usr/bin/env python3
"""TEMPORARY diagnostic: print the current season's sheet headers and, for the
first play that appears twice (once per team), the columns whose values differ.
Removed once the offense/defense marker column is known."""
import csv
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import pull_pace  # noqa: E402

text = pull_pace.fetch_csv(config.CURRENT_SEASON)
reader = csv.DictReader(io.StringIO(text))
fields = reader.fieldnames or []
print("HEADERS:", " | ".join(fields))
rows = list(reader)
print("ROWS:", len(rows))

groups = defaultdict(list)
for r in rows:
    groups[(r.get("GameId"), r.get("PlayId"))].append(r)
pairs = [g for g in groups.values() if len(g) == 2]
print("PLAYS LOGGED TWICE:", len(pairs), "of", len(groups))
for g in pairs[:2]:
    a, b = g
    diff = {c: (a.get(c), b.get(c)) for c in fields if a.get(c) != b.get(c)}
    print("DIFFERING COLUMNS:", diff)

for c in fields:
    vals = Counter((r.get(c) or "").strip() for r in rows)
    if len(vals) <= 6:
        print(f"LOW-CARDINALITY {c!r}: {dict(vals)}")
