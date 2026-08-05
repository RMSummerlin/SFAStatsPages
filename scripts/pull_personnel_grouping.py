#!/usr/bin/env python3
"""
Pull play-by-play data from the season Google Sheet and publish the data the
Personnel Grouping Frequency tools need.

Outputs (all under data/):
  personnel_grouping_<season>.json          encoded play-level data, one file per season
  personnel_grouping_index.json             which seasons exist + which is the default
  personnel_grouping_preload_compact.html   crawlable static table for the compact tool
  personnel_grouping_preload_full.html      crawlable static table for the full-grid tool

Why play-level instead of pre-aggregated: every filter (distance, score margin,
week, down, quarter, zone, personnel counts) is independent and combinable, so
there is no useful aggregation short of the plays themselves. Encoded columnar
(one character per play per field) it lands around 50 KB gzipped for a full
season, which GitHub Pages serves compressed. All filtering happens client-side
with no further requests.

Standard library only — nothing to install, so CI stays fast.

Usage:
  python scripts/pull_personnel_grouping.py                 # current season only
  python scripts/pull_personnel_grouping.py --all           # every season in config
  python scripts/pull_personnel_grouping.py --csv path.csv --season 2025   # local test
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Columns read from the sheet, by header name. New columns can be appended to the
# sheet on the right at any time without touching this script.
REQUIRED_COLUMNS = [
    "team", "week", "qtr", "down", "dist", "los",
    "PlayType", "PlayDesc", "Scramble?", "RBs", "TEs", "WRs", "ScoreDiff",
]

# Encoding alphabet: printable ASCII 35..126 minus backslash. 91 symbols, all
# JSON-safe without escaping, so one character carries values 0..90.
ALPHABET = "".join(chr(c) for c in range(35, 127) if c != 92)
BASE = len(ALPHABET)

MARGIN_OFFSET = 100  # margin is stored base-91 across two columns as margin + 100

FIELD_ZONES = ("Red zone", "20 to 50", "Own territory")


# --------------------------------------------------------------------------- io


def fetch_csv(season: int) -> str:
    url = config.csv_url(season)
    req = urllib.request.Request(url, headers={"User-Agent": "SFAStatsPages/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"Sheet for {season} returned HTTP {exc.code}. Confirm it is shared as "
            f'"Anyone with the link can view".\n  {url}'
        )
    text = raw.decode("utf-8-sig", errors="replace")
    if "accounts.google.com" in final_url or text.lstrip().startswith("<"):
        raise SystemExit(
            f"Sheet for {season} did not return CSV — it is probably not public. "
            f'Set sharing to "Anyone with the link can view".\n  {url}'
        )
    return text


def read_rows(text: str):
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(
            "Sheet is missing required column(s): "
            + ", ".join(missing)
            + "\nHeaders found: "
            + ", ".join(reader.fieldnames or [])
        )
    return list(reader)


# ---------------------------------------------------------------------- parsing


def as_int(value):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_week(value):
    """Sheet stores weeks as 'W1'...'W18'."""
    if value is None:
        return None
    return as_int(value.strip().lstrip("Ww"))


def field_zone(los):
    """los is yards from the opponent's goal line, 1-99."""
    if los <= 20:
        return 0            # inside the opponent 20
    if los <= 50:
        return 1            # opponent 20 out to midfield
    return 2                # the offense's own side of the field


def build_season(rows, season):
    """Clean and encode one season's rows. Returns (payload, per-team summary)."""
    plays = []
    dropped = Counter()

    for row in rows:
        play_type = (row.get("PlayType") or "").strip().upper()
        if play_type not in ("PASS", "RUSH"):
            dropped["not a pass or run"] += 1
            continue

        desc = (row.get("PlayDesc") or "").lower()
        if "kneel" in desc or "spike" in desc:
            dropped["kneel or spike"] += 1
            continue

        rb, te, wr = as_int(row.get("RBs")), as_int(row.get("TEs")), as_int(row.get("WRs"))
        if None in (rb, te, wr) or not 4 <= rb + te + wr <= 5:
            # 5 skill players is standard; 4 is a six-OL look. Anything else is
            # incomplete personnel data rather than a real grouping.
            dropped["incomplete personnel"] += 1
            continue

        team = (row.get("team") or "").strip().upper()
        week = parse_week(row.get("week"))
        qtr = as_int(row.get("qtr"))
        down = as_int(row.get("down"))
        dist = as_int(row.get("dist"))
        los = as_int(row.get("los"))
        margin = as_int(row.get("ScoreDiff"))

        if not team or None in (week, qtr, down, dist, los, margin):
            dropped["missing situation data"] += 1
            continue
        if not 1 <= los <= 99 or not 1 <= down <= 4 or qtr < 1:
            dropped["situation out of range"] += 1
            continue

        scramble = as_int(row.get("Scramble?")) == 1
        # Sacks are already coded PASS in the sheet; scrambles are coded RUSH.
        dropback = 1 if (play_type == "PASS" or scramble) else 0

        plays.append({
            "team": team,
            "week": week,
            "qtr": min(qtr, 5),            # 5 = overtime
            "down": down,
            "dist": max(1, min(dist, BASE - 1)),
            "zone": field_zone(los),
            "db": dropback,
            "pers": rb * 100 + te * 10 + wr,
            "margin": margin,
        })

    if not plays:
        raise SystemExit(f"No usable plays found for {season}. Check the sheet contents.")

    teams = sorted({p["team"] for p in plays})
    team_ix = {t: i for i, t in enumerate(teams)}
    pers_values = sorted({p["pers"] for p in plays})
    pers_ix = {v: i for i, v in enumerate(pers_values)}

    def enc(values):
        return "".join(ALPHABET[v] for v in values)

    margins = [p["margin"] for p in plays]
    m_shifted = [m + MARGIN_OFFSET for m in margins]
    if min(m_shifted) < 0 or max(m_shifted) >= BASE * BASE:
        raise SystemExit("Score margin outside the encodable range.")

    payload = {
        "schema": 1,
        "season": season,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plays": len(plays),
        "excluded": dict(dropped),
        "teams": teams,
        # personnel grouping as RB*100 + TE*10 + WR
        "pers": pers_values,
        "weeks": sorted({p["week"] for p in plays}),
        "dist_max": max(p["dist"] for p in plays),
        "margin_min": min(margins),
        "margin_max": max(margins),
        "zones": list(FIELD_ZONES),
        "alphabet": ALPHABET,
        "margin_offset": MARGIN_OFFSET,
        "cols": {
            "t": enc(team_ix[p["team"]] for p in plays),
            "w": enc(p["week"] for p in plays),
            "q": enc(p["qtr"] for p in plays),
            "d": enc(p["down"] for p in plays),
            "n": enc(p["dist"] for p in plays),
            "z": enc(p["zone"] for p in plays),
            "b": enc(p["db"] for p in plays),
            "p": enc(pers_ix[p["pers"]] for p in plays),
            "mh": enc(m // BASE for m in m_shifted),
            "ml": enc(m % BASE for m in m_shifted),
        },
    }

    summary = summarise(plays, teams)
    return payload, summary


def summarise(plays, teams):
    """Unfiltered season-to-date totals, used for the crawlable static tables."""
    totals = {t: Counter() for t in teams}
    grouping = {t: Counter() for t in teams}
    league = Counter()

    for p in plays:
        t, pers = p["team"], p["pers"]
        rb, te, wr = pers // 100, (pers // 10) % 10, pers % 10
        c = totals[t]
        c["plays"] += 1
        if rb >= 2:
            c["rb2"] += 1
        if te >= 2:
            c["te2"] += 1
        if wr >= 3:
            c["wr3"] += 1
        grouping[t][pers] += 1
        league[pers] += 1

    return {
        "teams": teams,
        "totals": {t: dict(totals[t]) for t in teams},
        "grouping": {t: dict(grouping[t]) for t in teams},
        "league": dict(league),
    }


# ------------------------------------------------------------- static html


def group_code(pers: int) -> int:
    """Standard personnel code: RB*10 + TE. 113 and 112 are both '11 personnel' —
    the second is a six-OL look, not a different grouping."""
    return (pers // 100) * 10 + (pers // 10) % 10


def pct(part, whole):
    return "0%" if not whole else f"{round(100 * part / whole)}%"


def preload_compact(summary, season):
    rows = []
    for t in summary["teams"]:
        c = summary["totals"][t]
        n = c.get("plays", 0)
        rows.append(
            "<tr><th scope=\"row\">{t}</th><td>{rb}</td><td>{te}</td>"
            "<td>{wr}</td><td>{n:,}</td></tr>".format(
                t=t, rb=pct(c.get("rb2", 0), n), te=pct(c.get("te2", 0), n),
                wr=pct(c.get("wr3", 0), n), n=n)
        )
    return (
        f'<table class="pt-pre"><caption>{season} personnel grouping frequency, '
        "all offensive plays, no filters applied</caption><thead><tr>"
        "<th scope=\"col\">Offense</th><th scope=\"col\">2+ RB</th>"
        "<th scope=\"col\">2+ TE</th><th scope=\"col\">3+ WR</th>"
        "<th scope=\"col\">Plays</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def preload_full(summary, season, max_columns=8):
    league = Counter()
    for pers, n in summary["league"].items():
        league[group_code(pers)] += n
    top = [g for g, _ in league.most_common(max_columns)]

    by_team = {}
    for team, groups in summary["grouping"].items():
        folded = Counter()
        for pers, n in groups.items():
            folded[group_code(pers)] += n
        by_team[team] = folded

    head = "".join(f'<th scope="col">{g:02d}</th>' for g in top)
    rows = []
    for t in summary["teams"]:
        n = summary["totals"][t].get("plays", 0)
        cells = "".join(f"<td>{pct(by_team[t].get(g, 0), n)}</td>" for g in top)
        rows.append(f'<tr><th scope="row">{t}</th>{cells}<td>{n:,}</td></tr>')
    return (
        f'<table class="pt-pre"><caption>{season} personnel grouping frequency by '
        "offense, all offensive plays, no filters applied. Groupings use the standard "
        "code: the first digit is running backs, the second is tight ends "
        '(so "12" is 1 RB and 2 TE).</caption>'
        f'<thead><tr><th scope="col">Offense</th>{head}'
        '<th scope="col">Plays</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


# ------------------------------------------------------------------------ main


def write_json(path: Path, obj) -> bool:
    """Write minified JSON. Returns True if the file content changed."""
    text = json.dumps(obj, separators=(",", ":"), sort_keys=False)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="rebuild every season in config, not just the current one")
    ap.add_argument("--csv", help="read from a local CSV instead of the sheet (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.csv:
        seasons = [args.season or config.CURRENT_SEASON]
    elif args.all:
        seasons = sorted(config.SEASON_SHEETS)
    else:
        seasons = [config.CURRENT_SEASON]

    newest_summary = None
    for season in seasons:
        if args.csv:
            text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
        else:
            text = fetch_csv(season)

        rows = read_rows(text)
        payload, summary = build_season(rows, season)

        # generated_utc changes every run, so compare on everything else to avoid
        # committing a no-op diff every 30 minutes.
        out = DATA_DIR / f"personnel_grouping_{season}.json"
        stamp = payload.pop("generated_utc")
        if out.exists():
            try:
                previous = json.loads(out.read_text(encoding="utf-8"))
                previous.pop("generated_utc", None)
                if previous == payload:
                    print(f"{season}: no change ({payload['plays']:,} plays)")
                    payload["generated_utc"] = stamp
                    if season == max(seasons):
                        newest_summary = (summary, season)
                    continue
            except (json.JSONDecodeError, OSError):
                pass
        payload["generated_utc"] = stamp
        write_json(out, payload)
        print(f"{season}: wrote {out.name} — {payload['plays']:,} plays, "
              f"excluded {sum(payload['excluded'].values()):,} "
              f"({payload['excluded']})")

        if season == max(seasons):
            newest_summary = (summary, season)

    known = sorted(
        int(p.stem.rsplit("_", 1)[1])
        for p in DATA_DIR.glob("personnel_grouping_*.json")
        if p.stem.rsplit("_", 1)[1].isdigit()
    )
    write_json(DATA_DIR / "personnel_grouping_index.json", {
        "seasons": known,
        "default": max(known) if known else None,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    if newest_summary:
        summary, season = newest_summary
        (DATA_DIR / "personnel_grouping_preload_compact.html").write_text(
            preload_compact(summary, season) + "\n", encoding="utf-8")
        (DATA_DIR / "personnel_grouping_preload_full.html").write_text(
            preload_full(summary, season) + "\n", encoding="utf-8")
        print("Refreshed crawlable preload tables in data/.")


if __name__ == "__main__":
    main()
