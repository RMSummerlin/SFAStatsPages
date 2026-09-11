#!/usr/bin/env python3
"""
Draft data/offseason_changes_<season>.json for the matchup tool.

The file tells pull_matchup.py which teams changed QB1, head coach, offensive
coordinator or defensive coordinator over the offseason, so it can cut the
weight of last season's rating for those units. Sources:

  QB1: nflverse games.csv. The new season's first-listed starter per team,
      against the most common starter in the prior season. Same source both
      sides, so names compare cleanly.
  HC, OC and DC: the Wikipedia navboxes "Template:NFL head coaches",
      "Template:NFL offensive coordinators" and "Template:NFL defensive
      coordinators", current revision against the last revision before the
      prior season ended. nflverse also carries a coach field, but it lags
      offseason hires (it still listed several fired coaches for 2026 week 1),
      so it is not used for that.

It is a DRAFT. Run it once in August, open the file, and correct anything that
looks wrong before the season starts. Interim coaches, a starter listed for week
1 who is not the real QB1, and any team missing from a navbox will show up as
oddities here. The pull script trusts the file as written.

Named without the pull_ prefix on purpose: it must never run on the schedule.

Usage:
  python scripts/offseason_changes.py --season 2026
  python scripts/offseason_changes.py --season 2026 --games games.csv   # offline nflverse copy
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
UA = {"User-Agent": "SFAStatsPages/1.0"}
NAME_TO_CODE = {v: k for k, v in config.TEAM_NAMES.items()}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def wiki_revision(title, before=None):
    p = {"action": "query", "prop": "revisions", "titles": title, "rvlimit": 1,
         "rvprop": "content|timestamp", "rvslots": "main", "format": "json"}
    if before:
        p.update({"rvstart": before, "rvdir": "older"})
    j = json.loads(get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(p)))
    rev = list(j["query"]["pages"].values())[0]["revisions"][0]
    return rev["timestamp"], rev["slots"]["main"]["*"]


def parse_navbox(text):
    out = {}
    for m in re.finditer(r"\*\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*\(\[\[(?:[^\]|]*\|)?([^\]]+)\]\]\)", text):
        name = m.group(2) or m.group(1)
        team = m.group(3).replace("List of ", "").replace(" head coaches", "")
        code = NAME_TO_CODE.get(team)
        if code:
            out[code] = name
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=config.CURRENT_SEASON)
    ap.add_argument("--games", help="local copy of nflverse games.csv")
    args = ap.parse_args()
    season, prior = args.season, args.season - 1

    text = Path(args.games).read_text(encoding="utf-8") if args.games else get(GAMES_URL)
    qb_prev = defaultdict(Counter)
    qb_new = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("game_type") != "REG":
            continue
        s = int(r["season"])
        for side in ("away", "home"):
            tm = config.canonical_team(r[f"{side}_team"])
            qb = r.get(f"{side}_qb_name") or ""
            if s == prior and qb:
                qb_prev[tm][qb] += 1
            elif s == season and int(r["week"]) == 1 and qb:
                qb_new.setdefault(tm, qb)

    cutoff = f"{season}-01-04T00:00:00Z"   # before the prior season's final week
    staff = {}
    for role, title in (("hc", "Template:NFL head coaches"),
                        ("oc", "Template:NFL offensive coordinators"),
                        ("dc", "Template:NFL defensive coordinators")):
        _, now = wiki_revision(title)
        _, old = wiki_revision(title, cutoff)
        staff[role] = (parse_navbox(now), parse_navbox(old))

    teams = {}
    for t in sorted(config.TEAM_NAMES):
        pq = qb_prev[t].most_common(1)[0][0] if qb_prev[t] else ""
        hc_now, hc_old = staff["hc"][0].get(t, ""), staff["hc"][1].get(t, "")
        oc_now, oc_old = staff["oc"][0].get(t, ""), staff["oc"][1].get(t, "")
        dc_now, dc_old = staff["dc"][0].get(t, ""), staff["dc"][1].get(t, "")
        teams[t] = {
            "qb": qb_new.get(t, ""), "qb_prev": pq, "qb_new": bool(qb_new.get(t)) and qb_new.get(t) != pq,
            "hc": hc_now, "hc_prev": hc_old, "hc_new": bool(hc_now) and hc_now != hc_old,
            "oc": oc_now, "oc_prev": oc_old, "oc_new": bool(oc_now) and oc_now != oc_old,
            "dc": dc_now, "dc_prev": dc_old, "dc_new": bool(dc_now) and dc_now != dc_old,
        }
    out = DATA_DIR / f"offseason_changes_{season}.json"
    out.write_text(json.dumps({
        "season": season,
        "note": "Draft from nflverse games.csv (QB, HC) and Wikipedia coordinator navboxes (OC, DC). "
                "Reviewed by an editor before the season; edit by hand, the pull trusts this file.",
        "teams": teams,
    }, indent=1) + "\n", encoding="utf-8")
    for t, v in teams.items():
        flags = [k for k in ("qb_new", "hc_new", "oc_new", "dc_new") if v[k]]
        print(f"{t}: {', '.join(flags) or 'no changes'}"
              + (f"  QB {v['qb_prev']} -> {v['qb']}" if v["qb_new"] else ""))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
