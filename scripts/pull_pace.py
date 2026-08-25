#!/usr/bin/env python3
"""
Pull play-by-play data from the season Google Sheet and publish the data the
Pace Statistics tool needs.

Outputs (all under data/):
  pace_<season>.json          encoded play- and drive-level data, one per season
  pace_index.json             which seasons exist + which is the default
  pace_preload.html           crawlable static table for the tool fragment

Why play-level instead of pre-aggregated: same reasoning as the personnel tool.
Every filter (week, quarter, down, home/road, huddle) is independent and
combinable, and the neutral / trailing splits have to be recomputed inside
whatever filter is active, so there is no useful aggregation short of the plays
themselves.

Tempo is measured as PLAY CLOCK USED: 40 minus the seconds left on the play
clock at the snap. See docs/pace-data.md for the derivation. The short version
is that snap-to-snap time bundles two different things — how long the previous
play took to finish, and how long the offence then took to snap. Only the second
is a tempo decision. Play clock used isolates it, and is 0.86 split-half reliable
against 0.74 for snap-to-snap.

TimeSinceSnap is still essential, but as a gate rather than a metric. Play clock
used is only comparable when the play clock started at 40, and the NFL resets to
25 after a change of possession, timeout, penalty, injury, measurement, review,
the two-minute warning and the start of a period. TimeSinceSnap is blank on
almost exactly that set — 96% of first-plays-of-drive, 94% of post-timeout snaps
— so requiring it to be present selects the 40-second universe without this
script having to enumerate the rule book. Verified: first plays of drives top out
at 25 on the play clock (4 exceptions in 5,692), while plays with TimeSinceSnap
present reach 39.

Penalties are the one case TimeSinceSnap does not catch. Those snaps keep a
TimeSinceSnap but run on a 25-second clock — their play clock maxes at exactly 25
across all 260 of them — so they are excluded explicitly.

Seasons whose sheet predates the TimeSinceSnap column are still published, with
pace fields absent and a loud warning in the log. The tool reads pace_index.json
and only offers seasons that actually carry tempo data, so a season starts
working the moment the column appears with no code change here.

Standard library only — nothing to install, so CI stays fast.

Usage:
  python scripts/pull_pace.py                          # current season only
  python scripts/pull_pace.py --all                    # every season in config
  python scripts/pull_pace.py --csv path.csv --season 2025   # local test
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import preloads  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Columns every season must have. Anything pace-specific that an older sheet
# might not carry goes in OPTIONAL_COLUMNS instead so the pull degrades rather
# than dying.
REQUIRED_COLUMNS = [
    "team", "opponent", "week", "qtr", "down", "PlayType", "PlayDesc",
    "ScoreDiff", "DriveNumber",
]

# Present in the 2025 sheet onward. A season missing TimeSinceSnap is published
# without tempo; a season missing the drive columns is published without volume.
OPTIONAL_COLUMNS = [
    "TimeSinceSnap", "PlayClock", "Huddle", "HomeRoad", "GameClock", "GameId",
    "PlayId", "DriveStartClock", "DriveEndClock", "DriveResult",
    "OffPenaltyYds", "DefPenaltyYds",
]

# Encoding alphabet: printable ASCII 35..126 minus backslash. 91 symbols, all
# JSON-safe without escaping, so one character carries values 0..90.
ALPHABET = "".join(chr(c) for c in range(35, 127) if c != 92)
BASE = len(ALPHABET)

MARGIN_OFFSET = 100   # margin stored base-91 across two columns as margin + 100

# A full play clock. Play clock used is PLAY_CLOCK - seconds remaining, so it is
# bounded 0..40 by construction and needs no winsorizing — which is the other
# reason to prefer it over snap-to-snap, whose tail ran to 75 seconds and had to
# be clipped. Only ever applied to plays that passed the 40-second gate.
PLAY_CLOCK = 40
# Values run 1..40, so 0 is free as the "no comparable snap" sentinel.
TEMPO_MISSING = 0

# Drives that ran out of clock rather than ending on their own terms. Their
# duration is an artifact of when the half started, not of how the offense
# operated, so they are excluded from seconds-per-drive and time of possession.
CLOCK_EXPIRED_RESULTS = {"End of Half", "End of Game"}

QUARTER_SECONDS = 900
LAST_TWO_MINUTES = 120

# Kneel-downs and clock-stopping spikes. Word-bounded deliberately: a plain
# substring test for "kneel" also matches DE M. Kneeland, who appears in tackle
# credits from 2024 on. PlayDesc carries player surnames, so any matcher on it
# needs boundaries. Shared with the personnel script by intent, duplicated by
# necessity — see scripts/test_pace.py, which pins the two together.
DEAD_BALL_RE = re.compile(r"\bkneels?\b|spiked the ball", re.IGNORECASE)

CLOCK_RE = re.compile(r"^\s*(\d{0,2}):(\d{2})\s*$")
# Team abbreviations are normalised centrally so every tool folds history the
# same way. Re-exported here because scripts/test_pace.py reaches them through
# this module.
TEAM_ALIASES = config.TEAM_ALIASES
canonical_team = config.canonical_team



# --------------------------------------------------------------------------- io


def google_token():
    """Mint a read-only access token from the service account key, if one is set.

    Returns (token, service_account_email), or (None, None) when the secret is
    absent — in which case the sheet is read anonymously. That fallback is
    deliberate: the pipeline keeps working while the sheet is still link-shared.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None, None

    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. Paste the whole key "
            "file including the outer { } braces."
        )
    if "client_email" not in info or "private_key" not in info:
        raise SystemExit(
            "GOOGLE_SERVICE_ACCOUNT_JSON is missing client_email or private_key. "
            "It should be the JSON key file, not the service account's email."
        )

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError:
        raise SystemExit(
            "google-auth and requests are needed to read a private sheet. "
            "Confirm they are listed in scripts/requirements.txt."
        )

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=config.SCOPES)
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
        raise SystemExit(
            f"Sheet for {season} returned HTTP {exc.code}. {hint}\n  {url}")

    text = raw.decode("utf-8-sig", errors="replace")
    if "accounts.google.com" in final_url or text.lstrip().startswith("<"):
        if account:
            raise SystemExit(
                f"Sheet for {season} returned a sign-in page instead of CSV.\n"
                f"  The service account {account} cannot see it.\n"
                f"  Open the sheet, click Share, and add that address as a Viewer.\n"
                f"  {url}")
        raise SystemExit(
            f"Sheet for {season} did not return CSV — it is not public and no "
            f"service account key is set.\n  {url}")
    return text


def read_rows(text: str):
    """Return (rows, set of optional columns present)."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise SystemExit(
            "Sheet is missing required column(s): "
            + ", ".join(missing)
            + "\nHeaders found: "
            + ", ".join(fields)
        )
    return list(reader), {c for c in OPTIONAL_COLUMNS if c in fields}


# ---------------------------------------------------------------------- parsing


def as_float(value):
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


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


def parse_clock(value):
    """'12:46' -> seconds remaining in the quarter. None if unparseable."""
    if value is None:
        return None
    m = CLOCK_RE.match(value)
    if not m:
        return None
    minutes = int(m.group(1) or 0)
    return minutes * 60 + int(m.group(2))


def drive_duration(start_clock, end_clock):
    """Elapsed seconds for a drive, handling the quarter boundary.

    Both clocks count down within their own quarter, so an end clock larger than
    the start clock means the drive crossed into the next quarter rather than
    running backwards. Verified against the 2025 sheet: 5,696 drives, zero
    negative and zero over a full quarter once this branch is applied.
    """
    if start_clock is None or end_clock is None:
        return None
    if end_clock <= start_clock:
        return start_clock - end_clock
    return start_clock + (QUARTER_SECONDS - end_clock)


def in_last_two_minutes(qtr, clock):
    """Final two minutes of either half — where the clock dictates tempo."""
    if qtr is None or clock is None:
        return False
    return qtr in (2, 4) and clock <= LAST_TWO_MINUTES


# ------------------------------------------------------------------- build


def mark_prior_penalties(rows, present):
    """Flag each row whose PREVIOUS play in the same drive drew a penalty.

    Those snaps run on a 25-second play clock, so their play clock used is not
    comparable with everyone else's. TimeSinceSnap does not blank them, so they
    have to be found here.

    Ordering matters and file order will not do: the sheet groups plays by team,
    so the two offences in a game are never interleaved. PlayId is a per-game
    sequence spanning both, which is the only ordering that means anything.
    """
    order = []
    for i, row in enumerate(rows):
        play_id = as_int(row.get("PlayId")) if "PlayId" in present else None
        order.append((row.get("GameId") or "", play_id if play_id is not None else i, i))
    order.sort()

    def drew_penalty(row):
        for col in ("OffPenaltyYds", "DefPenaltyYds"):
            yards = as_int(row.get(col))
            if yards:
                return True
        return "PENALTY" in (row.get("PlayDesc") or "").upper()

    previous = {}
    for _, _, i in order:
        row = rows[i]
        key = (row.get("GameId"), row.get("team"), row.get("DriveNumber"))
        row["_prior_penalty"] = previous.get(key, False)
        previous[key] = drew_penalty(row)


def build_season(rows, season, present):
    """Clean and encode one season. Returns (payload, summary)."""
    # Both columns are needed: PlayClock supplies the metric, TimeSinceSnap
    # selects the plays where that metric is comparable.
    has_tempo = "TimeSinceSnap" in present and "PlayClock" in present
    has_drives = {"DriveStartClock", "DriveEndClock", "DriveResult"} <= present
    has_order = "PlayId" in present

    plays = []
    dropped = Counter()
    renamed = Counter()
    capped = 0
    drives = {}

    for row in rows:
        play_type = (row.get("PlayType") or "").strip().upper()
        if play_type not in ("PASS", "RUSH"):
            dropped["not a pass or run"] += 1
            continue

        if DEAD_BALL_RE.search(row.get("PlayDesc") or ""):
            dropped["kneel or spike"] += 1
            continue

        team = canonical_team(row.get("team"))
        opp = canonical_team(row.get("opponent"))
        for raw, folded in ((row.get("team"), team), (row.get("opponent"), opp)):
            raw = (raw or "").strip().upper()
            if raw and raw != folded:
                renamed[raw + " \u2192 " + folded] += 1
        week = parse_week(row.get("week"))
        qtr = as_int(row.get("qtr"))
        down = as_int(row.get("down"))
        margin = as_int(row.get("ScoreDiff"))
        drive_no = as_int(row.get("DriveNumber"))

        if not team or not opp or None in (week, qtr, down, margin, drive_no):
            dropped["missing situation data"] += 1
            continue
        if not 1 <= down <= 4 or qtr < 1 or drive_no < 1:
            dropped["situation out of range"] += 1
            continue

        clock = parse_clock(row.get("GameClock"))
        play_id = as_int(row.get("PlayId"))

        # A blank TimeSinceSnap is information, not an error: the provider omits
        # it after every stoppage that also resets the play clock to 25. Such a
        # play still counts toward volume and is simply excluded from tempo.
        tempo_code = TEMPO_MISSING
        if has_tempo and as_float(row.get("TimeSinceSnap")) and not row.get("_prior_penalty"):
            remaining = as_float(row.get("PlayClock"))
            if remaining is not None and 0 <= remaining <= PLAY_CLOCK:
                used = int(round(PLAY_CLOCK - remaining))
                # A snap with the clock at 0 uses the whole 40; nothing can use
                # more, so the sentinel at 0 can never collide with a real value.
                tempo_code = min(max(used, 1), PLAY_CLOCK)
            elif remaining is not None:
                capped += 1

        huddle = (row.get("Huddle") or "").strip().lower()
        no_huddle = 1 if huddle.startswith("no") else 0
        home = 1 if (row.get("HomeRoad") or "").strip().lower().startswith("h") else 0

        plays.append({
            "team": team,
            "opp": opp,
            "week": week,
            "qtr": min(qtr, 5),                 # 5 = overtime
            "down": down,
            "drive": min(drive_no, BASE - 1),
            "tempo": tempo_code,
            "nh": no_huddle,
            "home": home,
            "l2": 1 if in_last_two_minutes(qtr, clock) else 0,
            "margin": margin,
            "order": play_id if play_id is not None else len(plays),
        })

        if has_drives:
            key = (team, week, min(drive_no, BASE - 1))
            if key not in drives:
                result = (row.get("DriveResult") or "").strip()
                seconds = drive_duration(
                    parse_clock(row.get("DriveStartClock")),
                    parse_clock(row.get("DriveEndClock")),
                )
                drives[key] = {
                    "team": team,
                    "week": week,
                    "drive": min(drive_no, BASE - 1),
                    "seconds": seconds,
                    # Clock-expired drives keep their play count but are excluded
                    # from duration, so they still count toward plays-per-drive.
                    "timed": 0 if result in CLOCK_EXPIRED_RESULTS else 1,
                }

    if not plays:
        raise SystemExit(f"No usable plays found for {season}. Check the sheet contents.")

    # File order groups plays by team, so the two offenses in a game are not
    # interleaved chronologically. PlayId is a per-game sequence spanning both
    # teams, which is the only thing that makes ordering meaningful. Nothing
    # downstream currently depends on it, but sorting here means a future metric
    # that does will be correct by construction rather than by accident.
    if has_order:
        plays.sort(key=lambda p: (p["week"], p["order"]))

    teams = sorted({p["team"] for p in plays})
    team_ix = {t: i for i, t in enumerate(teams)}
    # An opponent should always be a known team, but a stray value in the sheet
    # would otherwise raise a KeyError deep in the encoder.
    unknown_opponents = sorted({p["opp"] for p in plays} - set(teams))
    if unknown_opponents:
        raise SystemExit(
            f"{season}: opponent values with no matching team row: "
            + ", ".join(unknown_opponents)
        )

    drive_rows = sorted(drives.values(), key=lambda d: (d["week"], d["team"], d["drive"]))
    # A drive with an unparseable clock keeps its plays but contributes no time.
    untimed = sum(1 for d in drive_rows if d["seconds"] is None)
    for d in drive_rows:
        if d["seconds"] is None or not 0 <= d["seconds"] <= QUARTER_SECONDS * 4:
            d["seconds"] = 0
            d["timed"] = 0

    def enc(values):
        return "".join(ALPHABET[v] for v in values)

    def enc_wide(values, offset, label):
        shifted = [v + offset for v in values]
        if shifted and (min(shifted) < 0 or max(shifted) >= BASE * BASE):
            raise SystemExit(f"{label} outside the encodable range: "
                             f"{min(values)} to {max(values)}")
        return enc(v // BASE for v in shifted), enc(v % BASE for v in shifted)

    margins = [p["margin"] for p in plays]
    m_hi, m_lo = enc_wide(margins, MARGIN_OFFSET, "Score margin")
    d_hi, d_lo = enc_wide([d["seconds"] for d in drive_rows], 0, "Drive duration")

    payload = {
        "schema": 1,
        "season": season,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plays": len(plays),
        "drives": len(drive_rows),
        "excluded": dict(dropped),
        "renamed_teams": dict(renamed),
        "has_tempo": has_tempo,
        "has_drives": has_drives,
        "tempo_dropped": capped,
        "play_clock": PLAY_CLOCK,
        "drives_untimed": untimed,
        "teams": teams,
        "weeks": sorted({p["week"] for p in plays}),
        "margin_offset": MARGIN_OFFSET,
        "alphabet": ALPHABET,
        "cols": {
            "t": enc(team_ix[p["team"]] for p in plays),
            "o": enc(team_ix[p["opp"]] for p in plays),
            "w": enc(p["week"] for p in plays),
            "q": enc(p["qtr"] for p in plays),
            "d": enc(p["down"] for p in plays),
            "v": enc(p["drive"] for p in plays),
            "s": enc(p["tempo"] for p in plays),
            "n": enc(p["nh"] for p in plays),
            "hm": enc(p["home"] for p in plays),
            "l2": enc(p["l2"] for p in plays),
            "mh": m_hi,
            "ml": m_lo,
        },
        "dcols": {
            "t": enc(team_ix[d["team"]] for d in drive_rows),
            "w": enc(d["week"] for d in drive_rows),
            "v": enc(d["drive"] for d in drive_rows),
            "sh": d_hi,
            "sl": d_lo,
            "k": enc(d["timed"] for d in drive_rows),
        },
    }

    return payload, summarise(plays, drive_rows, teams)


def summarise(plays, drive_rows, teams):
    """Unfiltered season-to-date totals, used for the crawlable static table."""
    tempo = defaultdict(lambda: [0, 0])       # team -> [sum, count]
    neutral = defaultdict(lambda: [0, 0])
    trailing = defaultdict(lambda: [0, 0])
    counts = Counter()
    nohuddle = Counter()
    games = defaultdict(set)
    drive_keys = defaultdict(set)

    for p in plays:
        t = p["team"]
        counts[t] += 1
        nohuddle[t] += p["nh"]
        games[t].add(p["week"])
        drive_keys[t].add((p["week"], p["drive"]))

        if p["tempo"] == TEMPO_MISSING:
            continue
        tempo[t][0] += p["tempo"]
        tempo[t][1] += 1
        if p["qtr"] <= 3 and abs(p["margin"]) <= 14 and not p["l2"]:
            neutral[t][0] += p["tempo"]
            neutral[t][1] += 1
        if p["margin"] <= -5 and not p["l2"]:
            trailing[t][0] += p["tempo"]
            trailing[t][1] += 1

    seconds = defaultdict(int)
    timed = defaultdict(int)
    for d in drive_rows:
        if d["timed"]:
            seconds[d["team"]] += d["seconds"]
            timed[d["team"]] += 1

    def mean(pair):
        return round(pair[0] / pair[1], 2) if pair[1] else None

    out = {}
    for t in teams:
        n_games = len(games[t]) or 1
        n_drives = len(drive_keys[t]) or 1
        neu, tra = mean(neutral[t]), mean(trailing[t])
        out[t] = {
            "sec": mean(tempo[t]),
            "neutral": neu,
            "gear": (round(neu - tra, 2)
                     if neu is not None and tra is not None
                     and trailing[t][1] >= MIN_GEAR_PLAYS else None),
            "nohuddle": round(100 * nohuddle[t] / counts[t]) if counts[t] else 0,
            "plays": counts[t],
            "plays_game": round(counts[t] / n_games, 1),
            "plays_drive": round(counts[t] / n_drives, 2),
            "drives_game": round(n_drives / n_games, 2),
            "top_game": (round(seconds[t] / n_games / 60, 1) if timed[t] else None),
        }
    return {"teams": teams, "team": out}


# Below this many trailing plays the gear-change number is mostly sampling noise.
# Never binds at season level — the thinnest 2025 team has 113 — so it only takes
# effect once a filter narrows things down.
MIN_GEAR_PLAYS = 75


# ------------------------------------------------------------- static html


def fmt(value, suffix="", dash="—"):
    return dash if value is None else f"{value}{suffix}"


def preload_main(summary, season):
    """Crawlable table matching the shipped tool's Tempo mode."""
    rows = []
    ranked = sorted(
        summary["teams"],
        key=lambda t: (summary["team"][t]["neutral"] is None,
                       summary["team"][t]["neutral"] or 0),
    )
    for i, t in enumerate(ranked, 1):
        c = summary["team"][t]
        rows.append(
            f'<tr><td>{i}</td><th scope="row"><abbr title="{config.team_name(t)}">{t}</abbr> {config.team_name(t)}</th>'
            f'<td>{fmt(c["sec"])}</td>'
            f'<td>{fmt(c["neutral"])}</td>'
            f'<td>{fmt(c["gear"])}</td>'
            f'<td>{c["nohuddle"]}%</td>'
            f'<td>{c["plays_game"]}</td>'
            f'<td>{c["plays_drive"]}</td>'
            f'<td>{fmt(c["top_game"])}</td>'
            f'<td>{c["plays"]:,}</td></tr>'
        )
    return (
        f'<table class="pt-pre"><caption>{season} offensive pace by team, with no '
        "filters applied. Play clock used is how many of the 40 seconds an offense "
        "burns before snapping the ball, so it measures the huddle and the walk to "
        "the line rather than how long the previous play took to finish. Neutral "
        "covers quarters 1 to 3 inside 14 points, excluding the final two minutes "
        "of the half. Gear change is neutral play clock used minus play clock used "
        "when trailing by 5 or more, so a positive number means the offense speeds "
        "up once it falls behind. Lower is faster."
        "</caption>"
        '<thead><tr><th scope="col">#</th><th scope="col">Offense</th>'
        '<th scope="col">Play Clock Used (Sec/Play)</th>'
        '<th scope="col">Neutral Script (Sec/Play)</th>'
        '<th scope="col">Gear Change (Sec/Play)</th>'
        '<th scope="col">No Huddle (% of Plays)</th>'
        '<th scope="col">Plays per Game</th><th scope="col">Plays per Drive</th>'
        '<th scope="col">Time of Possession (Minutes)</th>'
        '<th scope="col">Plays</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


# ------------------------------------------------------------------------ main


def write_json(path: Path, obj) -> bool:
    text = json.dumps(obj, separators=(",", ":"), sort_keys=False) + "\n"
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
    tempo_seasons = []

    for season in seasons:
        if args.csv:
            text = Path(args.csv).read_text(encoding="utf-8-sig", errors="replace")
        else:
            text = fetch_csv(season)

        rows, present = read_rows(text)
        mark_prior_penalties(rows, present)
        missing = [c for c in OPTIONAL_COLUMNS if c not in present]
        if missing:
            print(f"{season}: NOTE — sheet has no {', '.join(missing)}. "
                  f"Publishing what is available.")

        payload, summary = build_season(rows, season, present)

        if payload["renamed_teams"]:
            for pair, n in sorted(payload["renamed_teams"].items()):
                print(f"{season}: pooled {pair} ({n:,} team-play references)")
        if len(payload["teams"]) != 32:
            print(f"{season}: NOTE — {len(payload['teams'])} teams, not 32: "
                  f"{', '.join(payload['teams'])}. If one of those is an "
                  f"alternate spelling, add it to TEAM_ALIASES in this script.")

        if payload["has_tempo"]:
            tempo_seasons.append(season)
        else:
            print(f"{season}: WARNING — no TimeSinceSnap column, so this season "
                  f"has no tempo data and the tool will not offer it. Add the "
                  f"column to the {season} sheet and re-run to enable it.")

        out = DATA_DIR / f"pace_{season}.json"
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
              f"{payload['drives']:,} drives, "
              f"{payload['tempo_dropped']:,} play-clock values out of range, "
              f"excluded {sum(payload['excluded'].values()):,} "
              f"({payload['excluded']})")

        if season == max(seasons):
            newest_summary = (summary, season)

    known = []
    for path in sorted(DATA_DIR.glob("pace_*.json")):
        stem = path.stem.rsplit("_", 1)[1]
        if not stem.isdigit():
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if blob.get("has_tempo"):
            known.append(int(stem))
    known.sort()

    write_json(DATA_DIR / "pace_index.json", {
        "seasons": known,
        "default": max(known) if known else None,
    })

    if newest_summary:
        summary, season = newest_summary
        (DATA_DIR / "pace_preload.html").write_text(
            preload_main(summary, season) + "\n", encoding="utf-8")
        print("Refreshed the crawlable preload table in data/.")
        if preloads.write_manifest():
            print("Rebuilt data/preloads.json for the WordPress shortcodes.")


if __name__ == "__main__":
    main()
