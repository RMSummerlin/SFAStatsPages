#!/usr/bin/env python3
"""
Pull play-by-play from the current and prior season Google Sheets, plus the
season schedule from nflverse, and publish what the Weekly Matchups tool needs.

Outputs (all under data/):
  matchup_<season>.json        schedule, the latest as-of snapshot in full, every
                               earlier snapshot's battle scores, and trend series
  matchup_<season>_w<W>.json   full detail for as-of week W (fetched on demand when
                               the reader steps back to an earlier week)
  matchup_index.json           which seasons exist + which is the default
  matchup_preload.html         crawlable slate table for the current week
  schedule_<season>.json       cached nflverse schedule, so a bad fetch does not
                               take the tool down
  matchup_prior_<season>.json  the prior season's per-team-game totals, so the
                               16 MB prior sheet is read once, not every 30 minutes

The rating model, in one paragraph. Every metric is a rate (numerator over
denominator). For as-of week W a team's rating blends this season's games with
last season: each past game at week t is weighted 0.5 ** ((W - t) / H), and last
season enters as one pseudo-observation at week 0 worth K games of plays, valued
at league_mean + r * (team_last_season - league_mean). Headline battle metrics
are also opponent-adjusted (iterative). The parameters were fitted by backtest on
2021 to 2025; see docs/matchup-data.md for the numbers and what they mean. The
short version: in-season decay barely matters, last season matters more than
intuition says but should be heavily regressed, and defense is far less
predictable than offense so its ratings are shrunk harder.

Snapshots are as-of: the week W card uses games with week < W only, and never
changes once W's games are in, so an old week stays honest about what was known.

Standard library only.

The prior season never changes once it is over, so its totals are cached in
data/matchup_prior_<season>.json after the first read and the sheet is not
fetched again. Pass --refresh-prior (or --all) to re-read it, for example after a
correction to last season's sheet.

Usage:
  python scripts/pull_matchup.py                            # current season
  python scripts/pull_matchup.py --refresh-prior            # re-read last season's sheet too
  python scripts/pull_matchup.py --all                      # every season in config
  python scripts/pull_matchup.py --csv cur.csv --prior-csv prev.csv --season 2026
  python scripts/pull_matchup.py --csv cur.csv --prior-csv prev.csv --season 2026 \
      --schedule data/schedule_2026.json                    # fully offline
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import preloads  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

TOOL = "matchup"
SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

REQUIRED_COLUMNS = [
    "team", "opponent", "week", "down", "dist", "PlayType", "PlayDesc",
    "EPA", "SuccessPlay", "Yds", "PlayResult", "PasserName",
]
# Anything a split needs that an older sheet might not carry. A missing column
# leaves that split empty rather than killing the pull.
OPTIONAL_COLUMNS = [
    "Scramble?", "PFFPrsrAlwd", "Blitz?", "PFFCoverageType", "PlayAct", "AirYds",
    "YdsPreCt", "YdsPostCt", "TTT", "Att",
]

# Same word-bounded pattern as pull_pace.py and pull_personnel_grouping.py.
DEAD_BALL_RE = re.compile(r"\bkneels?\b|spiked the ball", re.IGNORECASE)

WEEKS = 18
HALF_LIFE = 10.0          # games. Flat above 6 in the backtest; 10 is a light recency lean.
EXPLOSIVE_PASS = 15
EXPLOSIVE_RUSH = 10
DEEP_AIR = 20
MAN_COVERAGES = {"0", "1", "2M"}
ZONE_COVERAGES = {"2", "3", "4", "6"}
ADJUST_ITERATIONS = 3

# One row per metric the tool can show. K is the prior's weight in games,
# r how much of last season's deviation from average survives. Per side because
# the backtest found defense far less predictable than offense.
#   hi_good: for the OFFENSE, higher is better. Defense flips it.
#   adjust : opponent-adjust this metric (battle metrics only; splits are too thin)
#   split  : pop-out only, never a battle input
# Offense K=8 r=0.4 (SR 0.5) and defense K=14 r=0.2 come straight from the backtest;
# rushing and explosives take K=12 r=0.3 on offense since they retained less.
# Split metrics use larger K because their per-game samples are small.
M = {
    "sr":       dict(num="succ",       den="plays", hi_good=True,  adjust=True,  split=False, off=(8, 0.5),  dfn=(14, 0.2)),
    "epa":      dict(num="epa",        den="plays", hi_good=True,  adjust=True,  split=False, off=(8, 0.4),  dfn=(14, 0.2)),
    "db_sr":    dict(num="db_succ",    den="db",    hi_good=True,  adjust=True,  split=False, off=(8, 0.5),  dfn=(14, 0.2)),
    "db_epa":   dict(num="db_epa",     den="db",    hi_good=True,  adjust=True,  split=False, off=(10, 0.4), dfn=(14, 0.2)),
    "run_sr":   dict(num="run_succ",   den="run",   hi_good=True,  adjust=True,  split=False, off=(12, 0.3), dfn=(14, 0.2)),
    "run_epa":  dict(num="run_epa",    den="run",   hi_good=True,  adjust=True,  split=False, off=(12, 0.3), dfn=(14, 0.3)),
    "prsr":     dict(num="prsr",       den="db",    hi_good=False, adjust=True,  split=False, off=(10, 0.4), dfn=(10, 0.2)),
    "explo":    dict(num="explo",      den="plays", hi_good=True,  adjust=True,  split=False, off=(12, 0.3), dfn=(10, 0.2)),
    # splits (pop-out only)
    "early_sr": dict(num="early_succ", den="early", hi_good=True,  adjust=False, split=True,  off=(10, 0.5), dfn=(14, 0.2)),
    "third":    dict(num="third_conv", den="third", hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "sack":     dict(num="sack",       den="db",    hi_good=False, adjust=False, split=True,  off=(12, 0.4), dfn=(12, 0.2)),
    "blitz":    dict(num="blitz",      den="db",    hi_good=None,  adjust=False, split=True,  off=(12, 0.3), dfn=(8, 0.5)),
    "blitz_epa":dict(num="blitz_epa",  den="blitz", hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "man":      dict(num="man",        den="cov",   hi_good=None,  adjust=False, split=True,  off=(12, 0.3), dfn=(8, 0.5)),
    "man_epa":  dict(num="man_epa",    den="man",   hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "zone_epa": dict(num="zone_epa",   den="zone",  hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "pa":       dict(num="pa",         den="db",    hi_good=None,  adjust=False, split=True,  off=(8, 0.5),  dfn=(12, 0.3)),
    "pa_epa":   dict(num="pa_epa",     den="pa",    hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "deep":     dict(num="deep",       den="att",   hi_good=None,  adjust=False, split=True,  off=(8, 0.5),  dfn=(12, 0.3)),
    "deep_epa": dict(num="deep_epa",   den="deep",  hi_good=True,  adjust=False, split=True,  off=(14, 0.3), dfn=(14, 0.2)),
    "xpass":    dict(num="xpass",      den="db",    hi_good=True,  adjust=False, split=True,  off=(12, 0.3), dfn=(12, 0.2)),
    "xrun":     dict(num="xrun",       den="run",   hi_good=True,  adjust=False, split=True,  off=(12, 0.3), dfn=(12, 0.2)),
    "ybc":      dict(num="ybc",        den="run",   hi_good=True,  adjust=False, split=True,  off=(12, 0.3), dfn=(12, 0.2)),
    "yac_run":  dict(num="yac_run",    den="run",   hi_good=True,  adjust=False, split=True,  off=(12, 0.3), dfn=(12, 0.2)),
    "ttt":      dict(num="ttt",        den="ttt_n", hi_good=None,  adjust=False, split=True,  off=(8, 0.5),  dfn=(12, 0.3)),
}

# The five rows on the card. Each is a weighted sum of metric z-scores. Success
# rate carries more weight than EPA because it was the more stable input in the
# backtest (year-over-year 0.47 against 0.39; split-half 0.58 against 0.55).
BATTLES = [
    dict(key="overall",   label="Overall",     parts=[("sr", 0.6), ("epa", 0.4)]),
    dict(key="pass",      label="Passing",     parts=[("db_sr", 0.6), ("db_epa", 0.4)]),
    dict(key="rush",      label="Rushing",     parts=[("run_sr", 0.6), ("run_epa", 0.4)]),
    dict(key="pressure",  label="Pressure",    parts=[("prsr", 1.0)]),
    dict(key="explosive", label="Explosives",  parts=[("explo", 1.0)]),
]

# Offseason and mid-season change haircuts on the prior. Only the QB1 change was
# backtested (year-over-year correlation 0.16 with a new primary passer against
# 0.37 without). The coordinator haircuts are judgment calls and are documented
# as such in docs/matchup-data.md.
QB_NEW_K_SCALE = 0.5
QB_NEW_R = 0.2
COACH_NEW_R_SCALE = 0.75


# --------------------------------------------------------------------------- io


def google_token():
    """Mint a read-only access token from the service account key, if one is set."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None, None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON.")
    if "client_email" not in info or "private_key" not in info:
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON is missing client_email or private_key.")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError:
        raise SystemExit("google-auth and requests are needed to read a private sheet.")
    creds = service_account.Credentials.from_service_account_info(info, scopes=config.SCOPES)
    creds.refresh(Request())
    return creds.token, info["client_email"]


def fetch_csv(season: int) -> str:
    url = config.csv_url(season)
    token, account = google_token()
    headers = {"User-Agent": "SFAStatsPages/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
        print(f"{season}: reading sheet as {account}")
    else:
        print(f"{season}: reading sheet anonymously (no service account key set)")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
            final_url = resp.geturl()
    except urllib.error.HTTPError as exc:
        hint = (f"Share the sheet with {account} as a Viewer." if account
                else 'Confirm it is shared as "Anyone with the link can view".')
        raise SystemExit(f"Sheet for {season} returned HTTP {exc.code}. {hint}\n  {url}")
    text = raw.decode("utf-8-sig", errors="replace")
    if "accounts.google.com" in final_url or text.lstrip().startswith("<"):
        raise SystemExit(f"Sheet for {season} returned a sign-in page instead of CSV.\n  {url}")
    return text


def read_rows(text: str):
    """Return (rows, optional columns present). rows is None for an empty sheet."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    if not fields:
        return None, set()
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise SystemExit("Sheet is missing required column(s): " + ", ".join(missing)
                         + "\nHeaders found: " + ", ".join(fields))
    return list(reader), {c for c in OPTIONAL_COLUMNS if c in fields}


def fetch_schedule(season: int, cache: Path):
    """nflverse games.csv, trimmed to one season. Falls back to the cached copy."""
    try:
        req = urllib.request.Request(SCHEDULE_URL, headers={"User-Agent": "SFAStatsPages/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"{season}: schedule fetch failed ({exc}); using cached copy if present")
        return load_schedule(cache)
    games = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("season") != str(season) or r.get("game_type") != "REG":
            continue
        games.append({
            "id": r["game_id"], "w": int(r["week"]),
            "date": r["gameday"], "time": r.get("gametime") or "",
            "day": (r.get("weekday") or "")[:3],
            "away": config.canonical_team(r["away_team"]),
            "home": config.canonical_team(r["home_team"]),
            "neutral": (r.get("location") or "") == "Neutral",
            "stadium": r.get("stadium") or "",
            "as": as_int(r.get("away_score")), "hs": as_int(r.get("home_score")),
            "aqb": r.get("away_qb_name") or "", "hqb": r.get("home_qb_name") or "",
            "acoach": r.get("away_coach") or "", "hcoach": r.get("home_coach") or "",
        })
    if not games:
        print(f"{season}: nflverse has no regular-season games for {season} yet; using cached copy if present")
        return load_schedule(cache)
    games.sort(key=lambda g: (g["w"], g["date"], g["time"], g["id"]))
    write_json(cache, {"season": season, "source": SCHEDULE_URL, "games": games})
    return games


def load_schedule(cache: Path):
    if not cache.exists():
        return None
    try:
        return json.loads(cache.read_text(encoding="utf-8"))["games"]
    except (json.JSONDecodeError, OSError, KeyError):
        return None


# ---------------------------------------------------------------------- parsing


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse_week(v):
    m = re.search(r"(\d+)", v or "")
    return int(m.group(1)) if m else None


def truthy(v):
    return (v or "").strip().lower() in {"1", "1.0", "true", "yes", "y"}


# ------------------------------------------------------------------- aggregate


def aggregate(rows, present):
    """Per (team, week, side) numerators and denominators for every metric.

    Offense rows are keyed by the team with the ball; the same play is also
    credited to the opponent's defense, so every metric is mirrored for free.
    """
    agg = defaultdict(lambda: defaultdict(float))
    passers = defaultdict(lambda: defaultdict(int))
    opp_of = {}
    n_used = 0
    excluded = defaultdict(int)
    has = lambda c: c in present  # noqa: E731

    for row in rows:
        ptype = (row.get("PlayType") or "").strip().upper()
        if ptype not in ("PASS", "RUSH"):
            excluded["not pass or rush"] += 1
            continue
        if DEAD_BALL_RE.search(row.get("PlayDesc") or ""):
            excluded["kneel or spike"] += 1
            continue
        epa = as_float(row.get("EPA"))
        succ = as_int(row.get("SuccessPlay"))
        week = parse_week(row.get("week"))
        if epa is None or succ is None or week is None:
            excluded["missing EPA, success or week"] += 1
            continue
        team = config.canonical_team(row.get("team"))
        opp = config.canonical_team(row.get("opponent"))
        if not team or not opp:
            excluded["missing team"] += 1
            continue
        n_used += 1
        opp_of[(team, week)] = opp
        opp_of[(opp, week)] = team

        yds = as_float(row.get("Yds")) or 0.0
        down = as_int(row.get("down"))
        dist = as_float(row.get("dist"))
        result = (row.get("PlayResult") or "").strip().upper()
        scramble = has("Scramble?") and truthy(row.get("Scramble?"))
        dropback = ptype == "PASS" or scramble
        run = ptype == "RUSH" and not scramble
        is_pass = ptype == "PASS"

        c = {}
        c["plays"] = 1; c["epa"] = epa; c["succ"] = succ
        if down in (1, 2):
            c["early"] = 1; c["early_succ"] = succ
        if down == 3:
            c["third"] = 1
            if result in ("FIRST DOWN", "TD") or (dist is not None and yds >= dist):
                c["third_conv"] = 1
        if (ptype == "PASS" and yds >= EXPLOSIVE_PASS) or (ptype == "RUSH" and yds >= EXPLOSIVE_RUSH):
            c["explo"] = 1
        if dropback:
            c["db"] = 1; c["db_epa"] = epa; c["db_succ"] = succ
            if is_pass and yds >= EXPLOSIVE_PASS:
                c["xpass"] = 1
            if result == "SACK" or (row.get("Sacked") or "").strip():
                c["sack"] = 1
            if has("PFFPrsrAlwd") and truthy(row.get("PFFPrsrAlwd")):
                c["prsr"] = 1
            if has("Blitz?") and truthy(row.get("Blitz?")):
                c["blitz"] = 1; c["blitz_epa"] = epa
            if has("PFFCoverageType"):
                cov = (row.get("PFFCoverageType") or "").strip().upper()
                if cov in MAN_COVERAGES:
                    c["cov"] = 1; c["man"] = 1; c["man_epa"] = epa
                elif cov in ZONE_COVERAGES:
                    c["cov"] = 1; c["zone"] = 1; c["zone_epa"] = epa
            if has("PlayAct") and truthy(row.get("PlayAct")):
                c["pa"] = 1; c["pa_epa"] = epa
            if is_pass and has("AirYds"):
                air = as_float(row.get("AirYds"))
                att = (not has("Att")) or truthy(row.get("Att"))
                if att and air is not None:
                    c["att"] = 1
                    if air >= DEEP_AIR:
                        c["deep"] = 1; c["deep_epa"] = epa
            if has("TTT"):
                t = as_float((row.get("TTT") or "").rstrip("s"))
                if t is not None and 0 < t < 15:
                    c["ttt"] = t; c["ttt_n"] = 1
        if run:
            c["run"] = 1; c["run_epa"] = epa; c["run_succ"] = succ
            if yds >= EXPLOSIVE_RUSH:
                c["xrun"] = 1
            if has("YdsPreCt"):
                v = as_float(row.get("YdsPreCt"))
                if v is not None:
                    c["ybc"] = v
            if has("YdsPostCt"):
                v = as_float(row.get("YdsPostCt"))
                if v is not None:
                    c["yac_run"] = v
        if is_pass:
            name = (row.get("PasserName") or "").strip()
            if name:
                passers[team][name] += 1

        o = agg[(team, week, "off")]
        d = agg[(opp, week, "def")]
        for k, v in c.items():
            o[k] += v
            d[k] += v

    return agg, opp_of, passers, n_used, dict(excluded)


def prior_cache_path(prior_season):
    return DATA_DIR / f"matchup_prior_{prior_season}.json"


def save_prior_cache(prior_season, agg, passers, n_used):
    """Serialise the prior season's totals. Keys are 'TEAM|week|side'."""
    blob = {
        "season": prior_season, "plays": n_used,
        "agg": {f"{t}|{w}|{side}": dict(c) for (t, w, side), c in agg.items()},
        "passers": {t: dict(d) for t, d in passers.items()},
    }
    write_json(prior_cache_path(prior_season), blob)


def load_prior_cache(prior_season):
    """Returns (agg, passers, plays) or None if there is no usable cache."""
    path = prior_cache_path(prior_season)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        agg = defaultdict(lambda: defaultdict(float))
        for key, c in blob["agg"].items():
            t, w, side = key.split("|")
            agg[(t, int(w), side)] = defaultdict(float, c)
        passers = defaultdict(lambda: defaultdict(int))
        for t, d in blob["passers"].items():
            passers[t] = defaultdict(int, d)
        return agg, passers, int(blob.get("plays", 0))
    except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
        print(f"{prior_season}: prior cache unreadable ({exc}); re-reading the sheet")
        return None


def teams_in(agg):
    return sorted({k[0] for k in agg})


def season_totals(agg, teams, side):
    tot = {t: defaultdict(float) for t in teams}
    for (t, w, s), c in agg.items():
        if s != side:
            continue
        for k, v in c.items():
            tot[t][k] += v
    return tot


def rate(c, m):
    d = c.get(M[m]["den"], 0.0)
    return c.get(M[m]["num"], 0.0) / d if d > 0 else None


def league_stats(tot, m):
    """League mean (pooled over plays) and team-level sd for one metric/side."""
    num = sum(c.get(M[m]["num"], 0.0) for c in tot.values())
    den = sum(c.get(M[m]["den"], 0.0) for c in tot.values())
    mean = num / den if den > 0 else 0.0
    vals = [rate(c, m) for c in tot.values()]
    vals = [v for v in vals if v is not None]
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0.0
    return mean, sd


def avg_den_per_game(agg, side, m):
    d = [c.get(M[m]["den"], 0.0) for (t, w, s), c in agg.items() if s == side]
    d = [x for x in d if x > 0]
    return sum(d) / len(d) if d else 0.0


# ------------------------------------------------------------------- blending


def blend_week(agg, opp_of, teams, prior, W, side, m, flags):
    """Blended, opponent-adjusted rating for every team as of week W.

    Returns dict team -> dict(v=rating, n=weighted current plays, share=current
    data share, raw=season-to-date raw rate or None).
    """
    spec = M[m]
    K, r = spec["off"] if side == "off" else spec["dfn"]
    p = prior[side][m]
    mean, avg_den = p["mean"], p["avg_den"]
    opp_side = "def" if side == "off" else "off"

    # Per-team list of (weight, num, den, opponent) for games before W.
    games = {}
    for t in teams:
        lst = []
        for w in range(1, W):
            c = agg.get((t, w, side))
            if not c or c.get(spec["den"], 0.0) <= 0:
                continue
            wt = 0.5 ** ((W - w) / HALF_LIFE)
            lst.append((wt, c.get(spec["num"], 0.0), c.get(spec["den"], 0.0), opp_of.get((t, w))))
        games[t] = lst

    def prior_terms(t):
        k, rr = K, r
        f = flags.get(t, {})
        if side == "off":
            if f.get("qb_new"):
                k, rr = K * QB_NEW_K_SCALE, QB_NEW_R
            elif f.get("hc_new") or f.get("oc_new"):
                rr = r * COACH_NEW_R_SCALE
        else:
            if f.get("dc_new") or f.get("hc_new"):
                rr = r * COACH_NEW_R_SCALE
        pv = mean + rr * (p["team"].get(t, mean) - mean)
        kp = k * avg_den * (0.5 ** (W / HALF_LIFE))
        return pv, kp

    # Opponent strength comes from the other side's estimate of the same
    # metric, passed in by blend_all as flags["_opp"]; absent on the first pass.
    opp_est = flags.get("_opp", {}).get(m) if spec["adjust"] else None
    adj = {t: 0.0 for t in teams}
    if opp_est:
        adj = {t: (opp_est[t] - mean) if opp_est.get(t) is not None else 0.0 for t in teams}
    est = {}
    for t in teams:
        pv, kp = prior_terms(t)
        num = kp * pv
        den = kp
        for wt, n, d, opp in games[t]:
            num += wt * (n - adj.get(opp, 0.0) * d)
            den += wt * d
        est[t] = num / den if den > 0 else None

    out = {}
    for t in teams:
        raw_n = sum(d for _, n, d, _ in games[t])
        raw = (sum(n for _, n, d, _ in games[t]) / raw_n) if raw_n > 0 else None
        wn = sum(wt * d for wt, n, d, _ in games[t])
        pv, kp = prior_terms(t)
        share = wn / (wn + kp) if (wn + kp) > 0 else 0.0
        out[t] = dict(v=est[t], n=raw_n, share=share, raw=raw)
    return out


def blend_all(agg, opp_of, teams, prior, W, flags_off, flags_def):
    """Both sides, all metrics, with a proper opponent-adjustment exchange.

    Offense X is adjusted by the opponent's defense X and vice versa, so the
    two sides are solved together: blend both unadjusted, then re-blend each
    side against the other's latest estimate, a few times.
    """
    est = {"off": {}, "def": {}}
    for it in range(ADJUST_ITERATIONS + 1):
        for side, flags in (("off", flags_off), ("def", flags_def)):
            other = "def" if side == "off" else "off"
            f = dict(flags)
            f["_opp"] = {m: {t: est[other][m][t]["v"] for t in teams}
                         for m in est[other]} if est[other] else {}
            for m in M:
                if it > 0 and not M[m]["adjust"]:
                    continue
                est[side][m] = blend_week(agg, opp_of, teams, prior, W, side, m, f)
    return est


def zscore(v, mean, sd):
    if v is None or sd <= 0:
        return 0.0
    return (v - mean) / sd


def battle_scores(est, prior, teams, side):
    """Battle score per team where higher is always better for THIS unit."""
    out = {b["key"]: {} for b in BATTLES}
    for b in BATTLES:
        for t in teams:
            s = 0.0
            for m, wgt in b["parts"]:
                p = prior[side][m]
                z = zscore(est[side][m][t]["v"], p["mean"], p["sd"])
                good = M[m]["hi_good"]
                sign = 1.0 if good else -1.0
                if side == "def":
                    sign = -sign
                s += wgt * sign * z
            out[b["key"]][t] = s
    return out


def rank_desc(values):
    """Rank 1 = highest. Ties share a rank. Returns (rank, pct) per team."""
    items = sorted(values.items(), key=lambda kv: -kv[1])
    ranks, pcts = {}, {}
    n = len(items)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        r = i + 1
        for k in range(i, j + 1):
            ranks[items[k][0]] = r
            pcts[items[k][0]] = (n - r) / (n - 1) if n > 1 else 1.0
        i = j + 1
    return ranks, pcts


def metric_rank(est, side, m, teams):
    """Rank 1 = best for this unit, on the blended value."""
    vals = {}
    for t in teams:
        v = est[side][m][t]["v"]
        if v is None:
            continue
        good = M[m]["hi_good"]
        if good is None:
            # A tendency, not a quality: rank 1 = highest rate, both sides.
            vals[t] = v
            continue
        sign = 1.0 if good else -1.0
        if side == "def":
            sign = -sign
        vals[t] = sign * v
    if not vals:
        return {}
    ranks, _ = rank_desc(vals)
    return ranks


def prior_block(agg_prev, teams_prev):
    """Everything the blend needs from last season: mean, sd, per-team rate, avg den."""
    out = {"off": {}, "def": {}}
    for side in ("off", "def"):
        tot = season_totals(agg_prev, teams_prev, side)
        for m in M:
            mean, sd = league_stats(tot, m)
            out[side][m] = dict(
                mean=mean, sd=sd,
                avg_den=avg_den_per_game(agg_prev, side, m),
                team={t: (rate(tot[t], m) if rate(tot[t], m) is not None else mean) for t in teams_prev},
            )
    return out


def primary_passers(passers):
    return {t: max(d.items(), key=lambda kv: kv[1])[0] for t, d in passers.items() if d}


# ------------------------------------------------------------------ snapshots


def week_flags(schedule, changes, prev_passers, W, teams):
    """Per-team flags as of week W: upcoming starter, whether he is new, staff changes."""
    starters = {}
    first = {}
    for g in schedule:
        for tm, qb in ((g["away"], g["aqb"]), (g["home"], g["hqb"])):
            if not qb:
                continue
            first.setdefault(tm, qb)
            if g["w"] >= W and tm not in starters:
                starters[tm] = qb
    off, dfn = {}, {}
    for t in teams:
        ch = changes.get(t, {})
        qb = starters.get(t) or first.get(t) or ch.get("qb") or ""
        # An offseason flag comes from the changes file (reviewed by an editor).
        # A mid-season change is the schedule saying this week's starter is not
        # the one who opened the season.
        qb_new = bool(ch.get("qb_new"))
        qb_since = None
        if first.get(t) and qb and qb != first[t]:
            qb_new = True
            for g in schedule:
                tm_qb = g["aqb"] if g["away"] == t else g["hqb"] if g["home"] == t else None
                if tm_qb == qb and g["w"] < W:
                    qb_since = g["w"]
                    break
        off[t] = dict(qb=qb, qb_new=qb_new, qb_since=qb_since,
                      hc_new=bool(ch.get("hc_new")), oc_new=bool(ch.get("oc_new")),
                      hc=ch.get("hc", ""), oc=ch.get("oc", ""))
        dfn[t] = dict(dc_new=bool(ch.get("dc_new")), hc_new=bool(ch.get("hc_new")),
                      dc=ch.get("dc", ""), hc=ch.get("hc", ""))
    return off, dfn


def snapshot(agg, opp_of, teams, prior, W, flags_off, flags_def):
    est = blend_all(agg, opp_of, teams, prior, W, flags_off, flags_def)
    units = {}
    bs = {side: battle_scores(est, prior, teams, side) for side in ("off", "def")}
    ranks = {side: {b: rank_desc(bs[side][b]) for b in bs[side]} for side in bs}
    mranks = {side: {m: metric_rank(est, side, m, teams) for m in M} for side in ("off", "def")}
    games_used = {t: sum(1 for w in range(1, W) if (t, w, "off") in agg) for t in teams}
    for t in teams:
        units[t] = {}
        for side in ("off", "def"):
            b = {}
            for bt in BATTLES:
                k = bt["key"]
                # confidence = current-data share of the first part metric
                share = est[side][bt["parts"][0][0]][t]["share"]
                b[k] = [round(bs[side][k][t], 3), ranks[side][k][0][t],
                        round(ranks[side][k][1][t], 3), round(share, 3)]
            mm = {}
            for m in M:
                e = est[side][m][t]
                p = prior[side][m]
                mm[m] = [
                    None if e["v"] is None else round(e["v"], 4),
                    None if e["raw"] is None else round(e["raw"], 4),
                    int(e["n"]),
                    mranks[side][m].get(t),
                    round(p["team"].get(t, p["mean"]), 4),
                ]
            units[t][side] = {"b": b, "m": mm,
                              "f": flags_off[t] if side == "off" else flags_def[t],
                              "g": games_used[t]}
    league = {side: {m: [round(prior[side][m]["mean"], 4), round(prior[side][m]["sd"], 4)] for m in M}
              for side in ("off", "def")}
    return {"w": W, "units": units, "league": league}


def game_results(agg, schedule):
    """Actual per-unit numbers for games the sheet already has."""
    out = {}
    for g in schedule:
        a = agg.get((g["away"], g["w"], "off"))
        h = agg.get((g["home"], g["w"], "off"))
        if not a or not h:
            continue
        out[g["id"]] = {
            g["away"]: [round(a["epa"] / a["plays"], 3), round(a["succ"] / a["plays"], 3), int(a["plays"])],
            g["home"]: [round(h["epa"] / h["plays"], 3), round(h["succ"] / h["plays"], 3), int(h["plays"])],
        }
    return out


def current_week(schedule, today):
    """First week with a game still to be played. Flips the day after MNF."""
    for w in range(1, WEEKS + 1):
        if any(g["w"] == w and g["date"] >= today for g in schedule):
            return w
    return WEEKS


# ------------------------------------------------------------- static html


def preload_table(season, W, schedule, snap, names):
    week_games = [g for g in schedule if g["w"] == W]
    rows = []
    for g in week_games:
        for off, dfn in ((g["away"], g["home"]), (g["home"], g["away"])):
            o = snap["units"][off]["off"]["b"]
            d = snap["units"][dfn]["def"]["b"]
            cells = []
            for b in BATTLES:
                k = b["key"]
                edge = o[k][2] - d[k][2]
                cells.append(f"<td>{o[k][1]}</td><td>{d[k][1]}</td><td>{edge_label(edge)}</td>")
            gcls = f"g-{g['away']}-{g['home']}".lower()
            rows.append(
                f'<tr class="{gcls}"><th scope="row">{names.get(off, off)} offense vs {names.get(dfn, dfn)} defense</th>'
                f'<td>{g["day"]} {g["date"]}</td>' + "".join(cells) + "</tr>")
    heads = "".join(
        f'<th scope="col">{b["label"]} offense rank</th><th scope="col">{b["label"]} defense rank</th>'
        f'<th scope="col">{b["label"]} edge</th>' for b in BATTLES)
    return (
        f'<table class="pt-pre"><caption>Week {W} NFL matchups for the {season} season: '
        "how each offense ranks against the defense it faces in overall efficiency, "
        "passing, rushing, pressure and explosive plays. Ranks are 1 to 32, blended "
        "from this season's games and a regressed prior from last season, adjusted for "
        "opponents faced. Edge reads from the offense's side: a large offense edge means "
        "a strong unit against a weak one.</caption>"
        '<thead><tr><th scope="col">Matchup</th><th scope="col">Kickoff</th>' + heads +
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def edge_label(e):
    a = abs(e)
    if a >= 0.5:
        who = "offense" if e > 0 else "defense"
        return f"Big {who} edge"
    if a >= 0.25:
        who = "offense" if e > 0 else "defense"
        return f"{who.capitalize()} edge"
    return "Even"


# ------------------------------------------------------------------------ main


def write_json(path: Path, obj) -> bool:
    text = json.dumps(obj, separators=(",", ":"), sort_keys=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def load_changes(season):
    path = DATA_DIR / f"offseason_changes_{season}.json"
    if not path.exists():
        print(f"{season}: no data/offseason_changes_{season}.json; no QB or staff haircuts applied. "
              f"Build one with scripts/offseason_changes.py.")
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{season}: could not read offseason changes ({exc}); ignoring it")
        return {}
    return {config.canonical_team(k): v for k, v in blob.get("teams", {}).items()}


def build_season(season, cur_rows, cur_present, prior_data, schedule, today):
    agg_prev, passers_prev, n_prev = prior_data
    teams_prev = teams_in(agg_prev)
    if len(teams_prev) != 32:
        print(f"{season - 1}: NOTE {len(teams_prev)} teams, not 32: {', '.join(teams_prev)}. "
              f"Check TEAM_ALIASES in scripts/config.py.")
    prior = prior_block(agg_prev, teams_prev)

    if cur_rows:
        agg, opp_of, passers, n_cur, excluded = aggregate(cur_rows, cur_present)
    else:
        agg, opp_of, passers, n_cur, excluded = {}, {}, {}, 0, {}
    teams = sorted(set(teams_prev) | set(teams_in(agg)))
    if len(teams) != 32:
        print(f"{season}: NOTE {len(teams)} teams, not 32: {', '.join(teams)}.")

    played = sorted({w for (t, w, s) in agg})
    latest = max(played) if played else 0
    cw = current_week(schedule, today)
    # Snapshots for as-of weeks 1 .. latest+1. A card for any later week reads
    # the latest snapshot, since no more games have been played.
    changes = load_changes(season)
    prev_passers = primary_passers(passers_prev)
    snaps = {}
    for W in range(1, min(latest + 1, WEEKS) + 1):
        fo, fd = week_flags(schedule, changes, prev_passers, W, teams)
        snaps[W] = snapshot(agg, opp_of, teams, prior, W, fo, fd)
        print(f"{season}: as-of week {W} built ({sum(snaps[W]['units'][t]['off']['g'] for t in teams)} team-games)")

    latest_w = max(snaps)
    trend = {t: {"off": {}, "def": {}} for t in teams}
    for t in teams:
        for side in ("off", "def"):
            for b in BATTLES:
                trend[t][side][b["key"]] = [snaps[W]["units"][t][side]["b"][b["key"]][0] for W in sorted(snaps)]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    names = {t: config.team_name(t) for t in teams}
    main = {
        "season": season, "prior": season - 1, "tool": TOOL,
        "generated_utc": stamp, "plays": n_cur, "prior_plays": n_prev,
        "excluded": excluded, "current_week": cw, "latest_played_week": latest,
        "teams": teams, "names": names,
        "battles": [{"key": b["key"], "label": b["label"], "parts": b["parts"]} for b in BATTLES],
        "metrics": {m: {"num": M[m]["num"], "den": M[m]["den"], "hi_good": M[m]["hi_good"],
                        "split": M[m]["split"], "adjust": M[m]["adjust"],
                        "off": M[m]["off"], "def": M[m]["dfn"]} for m in M},
        "params": {"half_life": HALF_LIFE, "explosive_pass": EXPLOSIVE_PASS,
                   "explosive_rush": EXPLOSIVE_RUSH, "deep_air": DEEP_AIR,
                   "qb_new_k_scale": QB_NEW_K_SCALE, "qb_new_r": QB_NEW_R,
                   "coach_new_r_scale": COACH_NEW_R_SCALE},
        "schedule": schedule,
        "results": game_results(agg, schedule),
        "snapshot_weeks": sorted(snaps),
        "latest": snaps[latest_w],
        "battle_history": {str(W): {t: {side: {b["key"]: snaps[W]["units"][t][side]["b"][b["key"]]
                                              for b in BATTLES}
                                        for side in ("off", "def")}
                                    for t in teams}
                           for W in snaps if W != latest_w},
        "trend": trend,
    }
    per_week = {W: {"season": season, "generated_utc": stamp, **snaps[W]} for W in snaps if W != latest_w}
    preload = preload_table(season, cw, schedule, snaps[min(cw, latest_w)], names)
    return main, per_week, preload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild every season in config, not just the current one")
    ap.add_argument("--csv", help="read the current season from a local CSV (testing)")
    ap.add_argument("--prior-csv", help="read the prior season from a local CSV (testing)")
    ap.add_argument("--season", type=int, help="season label to use with --csv")
    ap.add_argument("--schedule", help="local schedule JSON to use instead of fetching nflverse")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD) for the current-week pick")
    ap.add_argument("--refresh-prior", action="store_true",
                    help="re-read the prior season's sheet instead of using data/matchup_prior_<season>.json")
    args = ap.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.csv:
        seasons = [args.season or config.CURRENT_SEASON]
    elif args.all:
        seasons = [s for s in sorted(config.SEASON_SHEETS) if s - 1 in config.SEASON_SHEETS]
    else:
        seasons = [config.CURRENT_SEASON]
    today = args.today or date.today().isoformat()

    built = []
    text_cache = {}

    def sheet_text(season):
        if season not in text_cache:
            text_cache[season] = fetch_csv(season)
        return text_cache[season]

    for season in seasons:
        if season - 1 not in config.SEASON_SHEETS and not args.prior_csv:
            print(f"{season}: no prior season sheet configured; the matchup tool needs one. Skipping.")
            continue
        prior_season = season - 1
        # The prior season is finished, so read it once and cache the totals.
        # --refresh-prior, --all and a local --prior-csv always re-read.
        prior_data = None
        prev_present = set()
        if not (args.refresh_prior or args.all or args.prior_csv):
            prior_data = load_prior_cache(prior_season)
            if prior_data:
                print(f"{prior_season}: using cached totals from {prior_cache_path(prior_season).name} "
                      f"({prior_data[2]:,} plays); pass --refresh-prior to re-read the sheet")
        if prior_data is None:
            if args.csv:
                prev_text = Path(args.prior_csv).read_text(encoding="utf-8-sig", errors="replace") if args.prior_csv else ""
            else:
                prev_text = sheet_text(prior_season)
            prev_rows, prev_present = read_rows(prev_text) if prev_text else (None, set())
            if not prev_rows:
                print(f"{season}: prior season {prior_season} has no rows; cannot build a prior. Skipping.")
                continue
            agg_prev, _, passers_prev, n_prev, _ = aggregate(prev_rows, prev_present)
            prior_data = (agg_prev, passers_prev, n_prev)
            save_prior_cache(prior_season, agg_prev, passers_prev, n_prev)
            print(f"{prior_season}: cached totals to {prior_cache_path(prior_season).name}")

        if args.csv:
            cur_text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
        else:
            cur_text = sheet_text(season)
        cur_rows, cur_present = read_rows(cur_text) if cur_text else (None, set())
        if not cur_rows:
            print(f"{season}: sheet has no rows yet; publishing a prior-only baseline.")
            cur_present = prev_present or set(OPTIONAL_COLUMNS)

        cache = DATA_DIR / f"schedule_{season}.json"
        if args.schedule:
            schedule = json.loads(Path(args.schedule).read_text(encoding="utf-8"))["games"]
        else:
            schedule = fetch_schedule(season, cache)
        if not schedule:
            print(f"{season}: no schedule available and no cached copy; skipping. "
                  f"The tool keeps whatever was published last.")
            continue

        main_blob, per_week, preload = build_season(
            season, cur_rows, cur_present, prior_data, schedule, today)

        out = DATA_DIR / f"matchup_{season}.json"
        stamp = main_blob.pop("generated_utc")
        # Round-trip through JSON before comparing: the blob holds tuples, the
        # file holds lists, and a tuple never equals a list in Python.
        main_blob = json.loads(json.dumps(main_blob))
        unchanged = False
        if out.exists():
            try:
                previous = json.loads(out.read_text(encoding="utf-8"))
                previous.pop("generated_utc", None)
                unchanged = previous == main_blob
            except (json.JSONDecodeError, OSError):
                pass
        main_blob["generated_utc"] = stamp
        if unchanged:
            print(f"{season}: no change ({main_blob['plays']:,} plays, current week {main_blob['current_week']})")
        else:
            write_json(out, main_blob)
            print(f"{season}: wrote {out.name}: {main_blob['plays']:,} plays, latest played week "
                  f"{main_blob['latest_played_week']}, current week {main_blob['current_week']}")
        for W, blob in per_week.items():
            write_json(DATA_DIR / f"matchup_{season}_w{W}.json", blob)
        built.append((season, preload))

    known = []
    for path in sorted(DATA_DIR.glob("matchup_*.json")):
        parts = path.stem.split("_")
        # matchup_2026.json only: not matchup_2026_w3.json, not matchup_prior_2025.json
        if len(parts) == 2 and parts[1].isdigit():
            known.append(int(parts[1]))
    known.sort()
    write_json(DATA_DIR / "matchup_index.json", {"seasons": known, "default": max(known) if known else None})

    if built:
        season, preload = max(built)
        (DATA_DIR / f"{TOOL}_preload.html").write_text(preload + "\n", encoding="utf-8")
        if preloads.write_manifest():
            print("Refreshed data/preloads.json.")
        print("Refreshed the crawlable preload table in data/.")


if __name__ == "__main__":
    main()
