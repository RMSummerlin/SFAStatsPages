#!/usr/bin/env python3
"""
Pull play-by-play data from the season Google Sheets and publish the data the
Pass Rate Over Expected tool needs.

Outputs (all under data/):
  proe_<season>.json          per team-week dropbacks, expected dropbacks and
                              plays, for the offense and for the defense it
                              faced, plus the schedule and byes
  proe_index.json             which seasons exist + which is the default
  proe_baseline.json          the league's dropback rate in every situation
                              bucket, counted per completed season
  proe_preload.html           crawlable static table for the tool fragment

Pass rate over expected (PROE) is a team's dropback rate minus the rate a
typical team would have had in the same situations, in percentage points. The
expectation is the LEAGUE'S dropback rate in the play's situation bucket:
down, distance band, field zone, clock state and score margin band, counted
over every completed season in scripts/config.py. No model, no betting line,
no win probability: a sceptical reader can rebuild every number from the
sheets with a pivot table. See docs/proe-data.md for how the buckets were
chosen and how the result compares with nflfastR's model.

Why the baseline is completed seasons only: the season in progress is measured
against a fixed league, so a team's number only moves when it plays, never
because the baseline it is measured against drifted. Each completed season sits
inside the pool it is compared with, which is deliberate: it answers "how did
this offense call plays against the league of its era" rather than against
one year's fashion. The in-progress season joins the pool once config.py has a
newer one, and the script notices and rebuilds every season when that happens.

Thin buckets fall back to coarser ones. The full key has about 3,400 cells and
some, such as fourth-and-long from the shadow of the posts with four minutes
left, hold a handful of plays. Below MIN_BUCKET plays the expectation comes
from the first coarser key with enough: drop the field zone, then the distance
band, then the margin band, then the clock state. A play's expected rate is
always taken from the finest key the league has actually populated.

Dropback means the play call was a pass: PlayType PASS (sacks already arrive
that way) plus scrambles, which the sheet codes RUSH with Scramble? set. Kneels
and spikes are excluded. Same definition as the pace tool's neutral pass rate.

Standard library only — nothing to install, so CI stays fast.

Usage:
  python scripts/pull_proe.py                          # current season only
  python scripts/pull_proe.py --all                    # every season in config
  python scripts/pull_proe.py --csv path.csv --season 2026   # local test
  python scripts/pull_proe.py --csv-dir exports/       # local multi-season test:
                                                       # reads <dir>/<season>.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import offense  # noqa: E402
import preloads  # noqa: E402
import pull_matchup as pm  # noqa: E402
import pull_pace as pp  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
TOOL = "proe"

# Fail loudly without these. The pull is useless if any is missing.
REQUIRED_COLUMNS = [
    "team", "opponent", "week", "qtr", "down", "dist", "los", "GameClock",
    "ScoreDiff", "PlayType", "PlayDesc",
]
# Scramble? is the one column that changes a number rather than enabling a
# feature: without it scrambles count as runs and every mobile quarterback's
# team reads a few points low. The pull still runs, with a warning.
OPTIONAL_COLUMNS = ["Scramble?", "GameId", "PlayId", "HomeRoad"]

WEEKS = 18
LAST_TWO_MINUTES = 120
LAST_FOUR_MINUTES = 240
# A bucket needs this many league plays before its rate is trusted. Below it the
# expectation comes from the next coarser key. 100 plays puts the standard
# error of a bucket rate under five points, which is the scale of the
# differences between teams.
MIN_BUCKET = 100

DEAD_BALL_RE = pm.DEAD_BALL_RE
canonical_team = config.canonical_team
as_float = pp.as_float
as_int = pp.as_int
parse_week = pp.parse_week
parse_clock = pp.parse_clock
truthy = pm.truthy


# ------------------------------------------------------------------ buckets
#
# Each feature is a short code so the full key reads like a sentence:
# "3|d7|C|q4|m1" is third-and-7-to-9, between the opponent's 49 and 21, in the
# fourth quarter with more than four minutes left, trailing by 4 to 8.


def dist_band(dist):
    if dist <= 1:
        return "d1"
    if dist <= 3:
        return "d2"
    if dist <= 6:
        return "d4"
    if dist <= 9:
        return "d7"
    if dist == 10:
        return "d10"
    return "d11"


def field_zone(los):
    """los is yards to the opponent's goal line, 1-99."""
    if los >= 80:
        return "A"      # own 1 to 20
    if los >= 50:
        return "B"      # own 21 to 50
    if los >= 21:
        return "C"      # opponent's 49 to 21
    return "D"          # red zone


def clock_state(qtr, clock):
    """qtr 1-5 (5 is overtime), clock is seconds left in the quarter."""
    if qtr >= 5:
        return "late"
    if qtr == 4:
        return "late" if clock <= LAST_FOUR_MINUTES else "q4"
    if qtr == 3:
        return "q3"
    if qtr == 2 and clock <= LAST_TWO_MINUTES:
        return "h1l"
    return "h1"


def margin_band(margin):
    """Offense's score minus the defense's."""
    if margin <= -17:
        return "m3"
    if margin <= -9:
        return "m2"
    if margin <= -4:
        return "m1"
    if margin <= 3:
        return "e"
    if margin <= 8:
        return "p1"
    if margin <= 16:
        return "p2"
    return "p3"


def bucket_key(down, dist, los, qtr, clock, margin):
    return "|".join([str(down), dist_band(dist), field_zone(los),
                     clock_state(qtr, clock), margin_band(margin)])


# The fall-back order. Each entry lists which of the five fields the key keeps,
# by position in the full key: down, distance, zone, clock, margin. The field
# zone goes first because it moves pass rate least; the clock state goes last
# because the two-minute and four-minute windows are the situations where
# nothing else predicts the call.
TIERS = [
    (0, 1, 2, 3, 4),
    (0, 1, 3, 4),
    (0, 3, 4),
    (0, 3),
    (0,),
]


def coarser(key, tier):
    parts = key.split("|")
    return "|".join(parts[i] for i in TIERS[tier])


class Baseline:
    """League dropback rate per bucket, with the tiered fall-back baked in."""

    def __init__(self, counts, seasons=()):
        # counts: {full key: [dropbacks, plays]} summed over every pooled season.
        self.seasons = list(seasons)
        self.tables = []
        for tier in range(len(TIERS)):
            table = defaultdict(lambda: [0, 0])
            for key, (p, n) in counts.items():
                k = coarser(key, tier)
                table[k][0] += p
                table[k][1] += n
            self.tables.append(table)
        self.plays = sum(n for _, n in counts.values())

    def expect(self, key):
        """(expected dropback probability, tier used)."""
        for tier, table in enumerate(self.tables):
            p, n = table.get(coarser(key, tier), (0, 0))
            if n >= MIN_BUCKET:
                return p / n, tier
        # Only reachable with almost no data at all, e.g. a local test on a
        # single week. Fall back to the league rate rather than failing.
        p, n = 0, 0
        for v in self.tables[-1].values():
            p += v[0]
            n += v[1]
        return (p / n if n else 0.5), len(TIERS)


# ------------------------------------------------------------------------ io


def read_rows(text):
    """Return (rows, set of optional columns present), or (None, set()) if empty."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if not fields:
        return None, set()
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise SystemExit("Sheet is missing required column(s): " + ", ".join(missing)
                         + "\nHeaders found: " + ", ".join(fields))
    return list(reader), {c for c in OPTIONAL_COLUMNS if c in fields}


def write_json(path, obj):
    text = json.dumps(obj, separators=(",", ":"), sort_keys=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


# ----------------------------------------------------------------- plays


def plays_from_rows(rows, present):
    """One dict per usable play: team, opp, week, pass flag and bucket key."""
    plays = []
    dropped = Counter()
    has_scramble = "Scramble?" in present
    for row in rows:
        ptype = (row.get("PlayType") or "").strip().upper()
        if ptype not in ("PASS", "RUSH"):
            dropped["not a pass or run"] += 1
            continue
        if DEAD_BALL_RE.search(row.get("PlayDesc") or ""):
            dropped["kneel or spike"] += 1
            continue
        team = canonical_team(row.get("team"))
        opp = canonical_team(row.get("opponent"))
        week = parse_week(row.get("week"))
        qtr = as_int(row.get("qtr"))
        down = as_int(row.get("down"))
        dist = as_float(row.get("dist"))
        los = as_float(row.get("los"))
        clock = parse_clock(row.get("GameClock"))
        margin = as_int(row.get("ScoreDiff"))
        if (not team or not opp or week is None or qtr is None or down is None
                or dist is None or los is None or clock is None or margin is None):
            dropped["missing situation data"] += 1
            continue
        if not (1 <= down <= 4 and 1 <= qtr <= 5 and 1 <= los <= 99
                and 1 <= week <= WEEKS and dist >= 0):
            dropped["situation out of range"] += 1
            continue
        scramble = has_scramble and truthy(row.get("Scramble?"))
        plays.append({
            "team": team, "opp": opp, "week": week,
            "pass": 1 if (ptype == "PASS" or scramble) else 0,
            "key": bucket_key(down, int(dist), int(los), qtr, clock, margin),
        })
    return plays, dropped


def bucket_counts(plays):
    counts = defaultdict(lambda: [0, 0])
    for p in plays:
        counts[p["key"]][0] += p["pass"]
        counts[p["key"]][1] += 1
    return {k: v for k, v in counts.items()}


# ------------------------------------------------------------------ season


def team_weeks(plays, baseline):
    """{team: {week: [passO, expO, nO, passD, expD, nD, opponent]}} and tier use."""
    tw = defaultdict(lambda: defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0, None]))
    tiers = Counter()
    for p in plays:
        e, tier = baseline.expect(p["key"])
        tiers[tier] += 1
        o = tw[p["team"]][p["week"]]
        o[0] += p["pass"]
        o[1] += e
        o[2] += 1
        o[6] = p["opp"]
        d = tw[p["opp"]][p["week"]]
        d[3] += p["pass"]
        d[4] += e
        d[5] += 1
        d[6] = p["team"]
    out = {}
    for team in sorted(tw):
        out[team] = {}
        for week in sorted(tw[team]):
            v = tw[team][week]
            out[team][str(week)] = [v[0], round(v[1], 2), v[2], v[3], round(v[4], 2), v[5], v[6]]
    return out, tiers


def proe_of(cells, side):
    """PROE in points over a list of team-week cells. side 0 = offense, 3 = defense."""
    p = sum(c[side] for c in cells)
    e = sum(c[side + 1] for c in cells)
    n = sum(c[side + 2] for c in cells)
    return (round(100 * (p - e) / n, 1) if n else None), n


def league_offset(tw):
    """The league's over-expected dropback rate, as a probability, over every
    play in the season. Subtracted from every figure so the league averages
    zero within each season: the expectation comes from a fixed pool of past
    seasons and the league drifts, so without this a run-heavy year reads a
    point below zero across the board. The offense sums cover every play, so
    the same offset serves the defense side."""
    p = e = n = 0.0
    for cells in tw.values():
        for c in cells.values():
            p += c[0]
            e += c[1]
            n += c[2]
    return (p - e) / n if n else 0.0


def centred(c, m):
    return [c[0], c[1] + m * c[2], c[2], c[3], c[4] + m * c[5], c[5], c[6]]


def summarise(tw, teams):
    """Season and last-four figures per team, both sides, centred on the
    league. For the preload table; the tool does the same sums in the browser."""
    m = league_offset(tw)
    out = {}
    for t in teams:
        cells = {w: centred(c, m) for w, c in tw.get(t, {}).items()}
        weeks = sorted(int(w) for w in cells)
        off_weeks = [w for w in weeks if cells[str(w)][2] > 0]
        def_weeks = [w for w in weeks if cells[str(w)][5] > 0]
        off_all = [cells[str(w)] for w in off_weeks]
        def_all = [cells[str(w)] for w in def_weeks]
        off_l4 = [cells[str(w)] for w in off_weeks[-4:]]
        def_l4 = [cells[str(w)] for w in def_weeks[-4:]]
        out[t] = {
            "off": proe_of(off_all, 0)[0], "off_n": proe_of(off_all, 0)[1],
            "off_l4": proe_of(off_l4, 0)[0],
            "def": proe_of(def_all, 3)[0], "def_n": proe_of(def_all, 3)[1],
            "def_l4": proe_of(def_l4, 3)[0],
            "games": len(off_weeks),
        }
    return out


def byes_from(schedule, teams):
    """{team: week} for every team missing from a week's games. Only weeks that
    look complete (at least 12 games) count, so a half-published schedule does
    not mark everybody as on a bye."""
    byes = {}
    if not schedule:
        return byes
    by_week = defaultdict(set)
    for g in schedule:
        by_week[g["w"]].add(g["away"])
        by_week[g["w"]].add(g["home"])
    for w in sorted(by_week):
        if len(by_week[w]) < 24:
            continue
        for t in teams:
            if t not in by_week[w] and t not in byes:
                byes[t] = w
    return byes


def build_season(season, plays, dropped, baseline, schedule, today):
    teams = sorted({p["team"] for p in plays} | {p["opp"] for p in plays})
    tw, tiers = team_weeks(plays, baseline)
    latest = max(p["week"] for p in plays)
    cw = pm.current_week(schedule, today) if schedule else min(latest + 1, WEEKS)
    sched = [{
        "id": g["id"], "w": g["w"], "date": g["date"], "time": g["time"], "day": g["day"],
        "away": g["away"], "home": g["home"], "as": g["as"], "hs": g["hs"],
    } for g in (schedule or [])]
    payload = {
        "schema": 1,
        "season": season,
        "tool": TOOL,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "plays": len(plays),
        "excluded": dict(dropped),
        "baseline": {"seasons": baseline.seasons, "plays": baseline.plays,
                     "min_bucket": MIN_BUCKET,
                     "tiers": [tiers.get(i, 0) for i in range(len(TIERS) + 1)]},
        "weeks": WEEKS,
        "current_week": cw,
        "latest_played_week": latest,
        "teams": teams,
        "names": {t: config.team_name(t) for t in teams},
        "schedule": sched,
        "byes": byes_from(sched, teams),
        "tw": tw,
    }
    return payload, summarise(tw, teams)


# ------------------------------------------------------------- static html


def fmt(v):
    if v is None:
        return "—"
    return f"{v:+.1f}"


def preload_table(season, summary, names):
    ranked = sorted(summary, key=lambda t: (summary[t]["off"] is None, -(summary[t]["off"] or 0)))
    rows = []
    for i, t in enumerate(ranked, 1):
        s = summary[t]
        rows.append(
            f'<tr><td>{i}</td><th scope="row">{names.get(t, t)}</th>'
            f'<td>{fmt(s["off"])}</td><td>{fmt(s["off_l4"])}</td>'
            f'<td>{fmt(s["def"])}</td><td>{fmt(s["def_l4"])}</td>'
            f'<td>{s["games"]}</td></tr>'
        )
    return (
        f'<table class="pt-pre"><caption>{season} NFL pass rate over expected by team. '
        "Pass rate over expected is an offense's dropback rate minus the rate a typical "
        "offense would have had in the same situations (down, distance, field position, "
        "clock and score), in percentage points, so a positive number means the team "
        "calls passes more often than the situations call for. Sacks and scrambles count "
        "as pass calls. Defense is the same figure for the offenses a defense faced. "
        "Last 4 covers the team's last four games. Figures are centred so the league "
        "averages zero for the season.</caption>"
        '<thead><tr><th scope="col">Rank</th><th scope="col">Team</th>'
        '<th scope="col">Offense PROE</th><th scope="col">Offense Last 4</th>'
        '<th scope="col">Defense PROE Against</th><th scope="col">Defense Last 4</th>'
        '<th scope="col">Games</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


# ------------------------------------------------------------------------ main


def load_text(season, args):
    if args.csv:
        return Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
    if args.csv_dir:
        path = Path(args.csv_dir) / f"{season}.csv"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8-sig", errors="replace")
    return pp.fetch_csv(season)


def season_plays(season, args):
    """(plays, dropped, note) for one season, or (None, None, reason) if empty."""
    text = load_text(season, args)
    if text is None:
        return None, None, "no local export"
    rows, present = read_rows(text)
    if not rows:
        return None, None, "sheet has no rows yet"
    rows, note = offense.offense_rows(rows)
    if note:
        print(f"{season}: {note}")
    if "Scramble?" not in present:
        print(f"{season}: WARNING — no Scramble? column, so scrambles count as runs "
              f"and mobile quarterbacks' teams will read low.")
    plays, dropped = plays_from_rows(rows, present)
    if not plays:
        return None, None, f"{len(rows):,} rows but no usable plays"
    return plays, dropped, None


def load_baseline_file():
    path = DATA_DIR / "proe_baseline.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="rebuild every season in config, not just the current one")
    ap.add_argument("--csv", help="read from a local CSV instead of the sheet (testing)")
    ap.add_argument("--csv-dir", help="read <dir>/<season>.csv for every season (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD) for the current-week pick")
    ap.add_argument("--out", help="write outputs here instead of data/ (testing)")
    args = ap.parse_args()

    global DATA_DIR
    if args.out:
        DATA_DIR = Path(args.out)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = args.today or date.today().isoformat()
    current = config.CURRENT_SEASON
    configured = sorted(config.SEASON_SHEETS)
    completed = [s for s in configured if s < current]

    # ---- which seasons to pull -------------------------------------------
    stored = load_baseline_file()
    stored_seasons = sorted(int(s) for s in (stored or {}).get("by_season", {}))
    if args.csv:
        seasons = [args.season or current]
        pooled_from = []                           # nothing to add to the pool
        need_all = False
    elif args.csv_dir:
        seasons = [s for s in configured if (Path(args.csv_dir) / f"{s}.csv").exists()]
        pooled_from = [s for s in seasons if s < current]
        need_all = True
    else:
        # The baseline must hold exactly the completed seasons. If it does not
        # (first run, or a season rolled over), every season has to be re-read
        # and re-published against the new pool.
        need_all = args.all or stored is None or stored_seasons != completed
        if need_all and not args.all and stored is not None:
            print(f"baseline covers {stored_seasons}, config says {completed}: rebuilding every season")
        seasons = configured if need_all else [current]
        pooled_from = completed

    # ---- read the plays ---------------------------------------------------
    loaded = {}
    dropped_by = {}
    for season in seasons:
        plays, dropped, reason = season_plays(season, args)
        if plays is None:
            print(f"{season}: {reason} — skipping. The season stays out of proe_index.json.")
            continue
        loaded[season] = plays
        dropped_by[season] = dropped

    if not loaded:
        print("No season produced any plays. Nothing written.")
        return

    # ---- the baseline -----------------------------------------------------
    by_season = {}
    if stored is not None and not need_all:
        by_season = {int(s): v for s, v in stored["by_season"].items()}
    for season in pooled_from:
        if season in loaded:
            by_season[season] = bucket_counts(loaded[season])
    if not by_season:
        # Local single-season test with no baseline on disk: measure the season
        # against itself and say so. Never happens on the schedule.
        only = max(loaded)
        print(f"{only}: NOTE — no baseline on disk, measuring the season against its own league rate.")
        by_season = {only: bucket_counts(loaded[only])}
    pooled = defaultdict(lambda: [0, 0])
    for season, counts in by_season.items():
        for key, (p, n) in counts.items():
            pooled[key][0] += p
            pooled[key][1] += n
    baseline = Baseline(dict(pooled), sorted(by_season))
    print(f"baseline: {baseline.plays:,} plays over {baseline.seasons}, "
          f"{len(pooled):,} buckets, {sum(1 for v in pooled.values() if v[1] >= MIN_BUCKET):,} "
          f"with {MIN_BUCKET}+ plays")
    if not args.csv and (need_all or stored_seasons != baseline.seasons):
        write_json(DATA_DIR / "proe_baseline.json", {
            "seasons": baseline.seasons, "min_bucket": MIN_BUCKET,
            "by_season": {str(s): by_season[s] for s in baseline.seasons},
        })

    # ---- publish each season ---------------------------------------------
    summaries = {}
    for season in sorted(loaded):
        plays = loaded[season]
        cache = DATA_DIR / f"schedule_{season}.json"
        if args.csv or args.csv_dir:
            # Local runs never touch the network; the matchup pull keeps a
            # cached schedule in the repo's data/ for every published season.
            schedule = pm.load_schedule(REPO_ROOT / "data" / f"schedule_{season}.json")
        else:
            schedule = pm.fetch_schedule(season, cache)
        if not schedule:
            print(f"{season}: no schedule available, so no byes and no matchups for this season.")
        payload, summary = build_season(season, plays, dropped_by[season], baseline, schedule, today)
        if len(payload["teams"]) != 32:
            print(f"{season}: NOTE — {len(payload['teams'])} teams, not 32: "
                  f"{', '.join(payload['teams'])}. If one of those is an alternate "
                  f"spelling, add it to TEAM_ALIASES in scripts/config.py.")
        tiers = payload["baseline"]["tiers"]
        print(f"{season}: {payload['plays']:,} plays, excluded {dict(dropped_by[season])}; "
              f"expectation from the full key on {100 * tiers[0] / max(1, payload['plays']):.1f}% "
              f"of plays, tiers {tiers}")
        out = DATA_DIR / f"proe_{season}.json"
        stamp = payload.pop("generated_utc")
        if out.exists():
            try:
                previous = json.loads(out.read_text(encoding="utf-8"))
                previous.pop("generated_utc", None)
                if previous == payload:
                    print(f"{season}: no change")
                    summaries[season] = (summary, payload["names"])
                    continue
            except (json.JSONDecodeError, OSError):
                pass
        payload["generated_utc"] = stamp
        write_json(out, payload)
        print(f"{season}: wrote {out.name}")
        summaries[season] = (summary, payload["names"])

    # ---- index and preload ----------------------------------------------
    known = []
    for path in sorted(DATA_DIR.glob("proe_*.json")):
        stem = path.stem.rsplit("_", 1)[1]
        if stem.isdigit():
            known.append(int(stem))
    known.sort()
    write_json(DATA_DIR / "proe_index.json", {"seasons": known, "default": max(known) if known else None})

    if summaries:
        season = max(summaries)
        summary, names = summaries[season]
        (DATA_DIR / "proe_preload.html").write_text(
            preload_table(season, summary, names) + "\n", encoding="utf-8")
        if preloads.write_manifest():
            print("Refreshed data/preloads.json.")


if __name__ == "__main__":
    main()
