#!/usr/bin/env python3
"""TEMPORARY diagnostic (second pass): evaluate ways of telling which of the two
rows logged for every play is the offense. Removed once a method is chosen."""
import csv
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import pull_pace  # noqa: E402

text = pull_pace.fetch_csv(config.CURRENT_SEASON)
reader = csv.DictReader(io.StringIO(text))
fields = reader.fieldnames or []
rows = list(reader)

def f(v):
    try:
        return float((v or "").strip())
    except ValueError:
        return None

# Union of columns that ever differ between the two copies of a play.
groups = defaultdict(list)
for r in rows:
    groups[(r["GameId"], r["PlayId"])].append(r)
differ = Counter()
for g in groups.values():
    if len(g) == 2:
        for c in fields:
            if g[0].get(c) != g[1].get(c):
                differ[c] += 1
print("COLUMNS THAT EVER DIFFER BETWEEN THE TWO COPIES:", dict(differ))
print("DriveResult values:", dict(Counter(r["DriveResult"] for r in rows)))
print("PlayResult values:", dict(Counter(r["PlayResult"] for r in rows)))
print("yds == Yds on all rows:", all((r["yds"] or "") == (r["Yds"] or "") for r in rows))
print("ids present: PasserID", sum(1 for r in rows if r["PasserID"].strip()),
      "RusherID", sum(1 for r in rows if r["RusherID"].strip()),
      "TargetID", sum(1 for r in rows if r["TargetID"].strip()))

SIDE_RE = re.compile(r"\b(?:to|at)\s+([A-Z]{2,3})\s+(\d{1,2})\b")
print("SAMPLE DESCRIPTIONS:")
for r in rows[:6]:
    print("   ", r["team"], r["opponent"], "los", r["los"], "yds", r["yds"], "|", r["PlayDesc"][:140])

# One perspective per game: the home team's rows carry every play.
games = defaultdict(list)
for r in rows:
    if (r["HomeRoad"] or "").strip().lower().startswith("h"):
        games[r["GameId"]].append(r)

side_match = Counter()
for gid, rs in sorted(games.items()):
    home = config.canonical_team(rs[0]["team"]); away = config.canonical_team(rs[0]["opponent"])
    rs.sort(key=lambda r: f(r["PlayId"]) or 0)
    drives = defaultdict(list)
    for r in rs:
        drives[int(f(r["DriveNumber"]))].append(r)
    # Player clustering
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    for d, plays in drives.items():
        ids = {r[c].strip() for r in plays for c in ("PasserID", "RusherID", "TargetID") if r[c].strip()}
        for i in ids:
            union(("d", d), ("p", i))
    clusters = {}
    print(f"GAME {gid}: home {home} away {away}, {len(drives)} drives")
    prev_margin = None
    for d in sorted(drives):
        plays = drives[d]
        votes = Counter()
        for r in plays:
            m = SIDE_RE.search(r["PlayDesc"] or "")
            los, yds = f(r["los"]), f(r["yds"])
            if not m or los is None or yds is None:
                votes["?"] += 1; continue
            side = config.canonical_team(m.group(1))
            if side not in (home, away):
                side_match["unknown side " + m.group(1)] += 1
                votes["?"] += 1; continue
            end = los - yds
            if end == 50:
                votes["?"] += 1; continue
            off = side if end > 50 else (away if side == home else home)
            votes["H" if off == home else "A"] += 1
        cl = find(("d", d))
        clusters.setdefault(cl, len(clusters))
        margin = f(plays[0]["ScoreDiff"])
        delta = None if prev_margin is None else margin - prev_margin
        prev_margin = margin
        q = plays[0]["qtr"]
        print(f"   drive {d:2d} q{q} n={len(plays):2d} desc-votes H{votes['H']} A{votes['A']} ?{votes['?']} "
              f"cluster {clusters[cl]} result {plays[-1]['DriveResult']!r} margin@start {margin} delta_from_prev {delta}")
print("SIDE PARSE ISSUES:", dict(side_match))
