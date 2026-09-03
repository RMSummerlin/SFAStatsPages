#!/usr/bin/env python3
"""
A season whose sheet exists but has no data must not reach the front end.

The 2026 sheet was added to config.py well before the season started, so for a
couple of weeks every scheduled run pulled an empty sheet. Three things have to
hold for that to be harmless, and all three are easy to break by accident:

  1. An empty sheet is skipped, not treated as a fatal error. Otherwise the
     workflow fails every 30 minutes and takes the other tools down with it.
  2. No JSON is written for the season, so it stays out of the index the tools
     read, so it never appears in a season dropdown.
  3. The crawlable preload table is still rebuilt from the newest season that
     *does* have data. The obvious implementation keys the preload off
     max(seasons), which is the empty season, and quietly stops refreshing it.

Point 3 is the one that fails silently: the tools keep working, and the only
symptom is that the table search engines read slowly goes stale.

A sheet with the wrong headers is a different thing entirely and must still fail
loudly, so that is checked here too.

Runs offline — the sheet fetch is replaced with canned CSV text.

  python scripts/test_empty_season.py
"""

from __future__ import annotations

import csv
import io
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import preloads  # noqa: E402
import pull_pace  # noqa: E402
import pull_personnel_grouping  # noqa: E402

TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
         "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
         "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
         "TEN", "WAS"]

failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  ok    {label}")
    else:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


# ------------------------------------------------------------- fake sheets


def pace_csv() -> str:
    rnd = random.Random(7)
    cols = pull_pace.REQUIRED_COLUMNS + pull_pace.OPTIONAL_COLUMNS
    rows = []
    play = 0
    for game, (home, away) in enumerate(zip(TEAMS[::2], TEAMS[1::2])):
        for drive in range(1, 9):
            off, deff = (home, away) if drive % 2 else (away, home)
            for snap in range(1, 7):
                play += 1
                rows.append({
                    "team": off, "opponent": deff, "week": 1,
                    "qtr": min(4, 1 + drive // 3), "down": 1 + snap % 4,
                    "PlayType": rnd.choice(["PASS", "RUSH"]),
                    "PlayDesc": "a routine play for testing",
                    "ScoreDiff": 0, "DriveNumber": drive,
                    "TimeSinceSnap": "" if snap == 1 else rnd.randint(18, 40),
                    "PlayClock": rnd.randint(1, 20), "Huddle": "Huddle",
                    "HomeRoad": "Home" if off == home else "Road",
                    "GameClock": "12:00", "GameId": f"g{game}", "PlayId": play,
                    "DriveStartClock": "12:00", "DriveEndClock": "09:30",
                    "DriveResult": "Punt", "OffPenaltyYds": 0,
                    "DefPenaltyYds": 0, "Scramble?": "",
                })
    return to_csv(cols, rows)


def personnel_csv() -> str:
    rnd = random.Random(7)
    cols = pull_personnel_grouping.REQUIRED_COLUMNS
    rows = []
    for team in TEAMS:
        for snap in range(60):
            backs, ends = rnd.choice([(1, 1), (1, 2), (2, 1), (1, 3), (2, 2)])
            rows.append({
                "team": team, "week": 1, "qtr": 1 + snap % 4, "down": 1 + snap % 4,
                "dist": 10, "los": 50, "PlayType": rnd.choice(["PASS", "RUSH"]),
                "PlayDesc": "a routine play for testing", "Scramble?": "",
                "RBs": backs, "TEs": ends, "WRs": 5 - backs - ends,
                "ScoreDiff": 0, "EPA": round(rnd.uniform(-2, 2), 3),
                "yds": rnd.randint(-3, 15), "SuccessPlay": rnd.choice([0, 1]),
            })
    return to_csv(cols, rows)


def to_csv(cols, rows) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, cols, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def headers_only(text: str) -> str:
    return text.split("\n", 1)[0] + "\n"


# ------------------------------------------------------------------- driver


def run(module, sheets, tmp: Path, argv):
    """Run a pull script against canned sheets, writing into a temp data dir."""
    module.DATA_DIR = tmp
    preloads.DATA_DIR = tmp
    preloads.MANIFEST = tmp / "preloads.json"
    config.SEASON_SHEETS = dict(sheets)
    module.fetch_csv = lambda season: sheets[season]
    saved, sys.argv = sys.argv, argv
    try:
        module.main()
    finally:
        sys.argv = saved


def index_seasons(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["seasons"]


def case(name, module, prefix, sheets, argv, tmpdir):
    tmp = Path(tmpdir) / name
    tmp.mkdir(parents=True)
    run(module, sheets, tmp, argv)
    return tmp, index_seasons(tmp / f"{prefix}_index.json")


def main():
    pace, personnel = pace_csv(), personnel_csv()

    specs = [
        ("pace", pull_pace, "pace", pace),
        ("personnel", pull_personnel_grouping, "personnel_grouping", personnel),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        for label, module, prefix, good in specs:
            print(f"\n{label}:")

            # 1. A blank sheet, and a sheet with headers and no rows, are both
            #    skipped rather than published or crashed on.
            for kind, text in (("blank", ""), ("headers only", headers_only(good))):
                tmp, seasons = case(f"{label}-{kind.split()[0]}", module, prefix,
                                    {2026: text}, [f"pull_{prefix}.py"], tmpdir)
                check(f"{kind} sheet writes no season file",
                      not (tmp / f"{prefix}_2026.json").exists())
                check(f"{kind} sheet leaves the season out of the index",
                      not seasons, f"index says {seasons}")

            # 2. A sheet with the wrong headers still fails loudly.
            try:
                case(f"{label}-wrong", module, prefix,
                     {2026: "team,week\nARI,1\n"}, [f"pull_{prefix}.py"], tmpdir)
                check("wrong headers fail loudly", False, "no SystemExit raised")
            except SystemExit as exc:
                check("wrong headers fail loudly", "missing required column" in str(exc),
                      str(exc)[:60])

            # 3. Real data still publishes, and an empty newer season alongside
            #    it neither appears in the index nor stops the preload refresh.
            tmp, seasons = case(f"{label}-mixed", module, prefix,
                                {2025: good, 2026: ""},
                                [f"pull_{prefix}.py", "--all"], tmpdir)
            check("season with data is published", seasons == [2025],
                  f"index says {seasons}")
            check("empty newer season writes no file",
                  not (tmp / f"{prefix}_2026.json").exists())
            preload = tmp / f"{prefix}_preload.html"
            check("preload still refreshed from the newest season with data",
                  preload.exists() and preload.stat().st_size > 0)
            check("preload is built from the season with data, not the empty one",
                  preload.exists() and "2026" not in preload.read_text(encoding="utf-8"))

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nok    test_empty_season.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
