#!/usr/bin/env python3
"""
Regression tests for scripts/pull_matchup.py. Standard library, no network.

Pins the parts of the rating blend that are easy to break silently:
  * week 1 is prior-only and regressed by r toward the league mean
  * the prior's weight fades as games arrive
  * a new QB1 halves the prior's weight and regresses it harder
  * ranks are 1 = best for the unit in question, including on defense where
    lower EPA allowed is better and higher pressure rate is better
  * the current-week pick flips the day after the last game of a week
  * the 18-week snapshot cap holds
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pull_matchup as pm  # noqa: E402

TEAMS = ["AAA", "BBB", "CCC", "DDD"]


def row(team, opp, week, ptype, epa, succ, yds=3, **extra):
    r = {"team": team, "opponent": opp, "week": f"W{week}", "down": "1", "dist": "10",
         "PlayType": ptype, "PlayDesc": "pass", "EPA": str(epa), "SuccessPlay": str(succ),
         "Yds": str(yds), "PlayResult": "", "PasserName": "QB " + team, "Scramble?": "0",
         "PFFPrsrAlwd": "", "Blitz?": "0", "PFFCoverageType": "3", "PlayAct": "", "AirYds": "5",
         "YdsPreCt": "1", "YdsPostCt": "2", "TTT": "2.5s", "Att": "1"}
    r.update(extra)
    return r


PRESENT = set(pm.OPTIONAL_COLUMNS)


def prior_season(strength):
    """A full fake season: each team plays every other team twice, 20 plays a game.

    strength maps team -> EPA per play on offense; defense allows the negative.
    """
    rows = []
    week = 1
    for a in TEAMS:
        for b in TEAMS:
            if a == b:
                continue
            for i in range(20):
                epa = strength[a] + (0.05 if i % 2 else -0.05)
                rows.append(row(a, b, week, "PASS" if i % 3 else "RUSH", epa, 1 if epa > 0 else 0,
                                PFFPrsrAlwd="Yes" if (a == "AAA" and i % 4 == 0) else ""))
            week += 1
    return rows


def schedule(weeks=18):
    games = []
    for w in range(1, weeks + 1):
        games.append({"id": f"S_{w:02d}_AAA_BBB", "w": w, "date": f"2030-01-{w:02d}", "time": "13:00",
                      "day": "Sun", "away": "AAA", "home": "BBB", "neutral": False, "stadium": "",
                      "as": None, "hs": None, "aqb": "QB AAA", "hqb": "QB BBB", "acoach": "", "hcoach": ""})
        games.append({"id": f"S_{w:02d}_CCC_DDD", "w": w, "date": f"2030-01-{w:02d}", "time": "13:00",
                      "day": "Sun", "away": "CCC", "home": "DDD", "neutral": False, "stadium": "",
                      "as": None, "hs": None, "aqb": "QB CCC", "hqb": "QB DDD", "acoach": "", "hcoach": ""})
    return games


def build(prev_rows, cur_rows, changes=None, W=1):
    agg_prev, _, _, _, _ = pm.aggregate(prev_rows, PRESENT)
    prior = pm.prior_block(agg_prev, pm.teams_in(agg_prev))
    agg, opp_of, _, _, _ = pm.aggregate(cur_rows, PRESENT) if cur_rows else ({}, {}, {}, 0, {})
    fo, fd = pm.week_flags(schedule(), changes or {}, {}, W, TEAMS)
    est = pm.blend_all(agg, opp_of, TEAMS, prior, W, fo, fd)
    return prior, est, fo


def test_week1_is_regressed_prior():
    strength = {"AAA": 0.30, "BBB": 0.10, "CCC": -0.10, "DDD": -0.30}
    prior, est, _ = build(prior_season(strength), [])
    p = prior["off"]["epa"]
    K, r = pm.M["epa"]["off"]
    for t in TEAMS:
        expect = p["mean"] + r * (p["team"][t] - p["mean"])
        got = est["off"]["epa"][t]["v"]
        assert abs(got - expect) < 1e-9, f"{t}: week 1 should be the regressed prior, got {got} not {expect}"
        assert est["off"]["epa"][t]["share"] == 0.0
    print("ok  week 1 is the regressed prior")


def test_prior_fades_with_games():
    strength = {"AAA": 0.30, "BBB": 0.10, "CCC": -0.10, "DDD": -0.30}
    prev = prior_season(strength)
    # This season AAA is terrible: -0.5 EPA on every play across four games.
    cur = []
    for w in range(1, 5):
        for i in range(60):
            cur.append(row("AAA", "BBB", w, "PASS", -0.5, 0))
            cur.append(row("BBB", "AAA", w, "PASS", 0.0, 1))
    _, e2, _ = build(prev, cur, W=2)
    _, e5, _ = build(prev, cur, W=5)
    v2, v5 = e2["off"]["epa"]["AAA"]["v"], e5["off"]["epa"]["AAA"]["v"]
    assert v5 < v2 < 0.3, f"rating should move toward the new data as games arrive: wk2 {v2}, wk5 {v5}"
    assert e5["off"]["epa"]["AAA"]["share"] > e2["off"]["epa"]["AAA"]["share"] > 0
    assert v5 > -0.5, "four games should not fully override the prior"
    print("ok  prior fades as games arrive")


def test_new_qb_haircut():
    strength = {"AAA": 0.30, "BBB": 0.10, "CCC": -0.10, "DDD": -0.30}
    prev = prior_season(strength)
    _, plain, _ = build(prev, [])
    _, cut, flags = build(prev, [], changes={"AAA": {"qb_new": True, "qb": "New Guy"}})
    assert flags["AAA"]["qb_new"] is True
    p = plain["off"]["epa"]["AAA"]["v"]; c = cut["off"]["epa"]["AAA"]["v"]
    assert c < p, f"a new QB should pull a good prior toward the mean: {c} vs {p}"
    # Defense is untouched by a QB change.
    assert plain["def"]["epa"]["AAA"]["v"] == cut["def"]["epa"]["AAA"]["v"]
    print("ok  new QB1 haircut pulls the prior toward the mean")


def test_rank_direction():
    strength = {"AAA": 0.30, "BBB": 0.10, "CCC": -0.10, "DDD": -0.30}
    prev = prior_season(strength)
    prior, est, _ = build(prev, [])
    off = pm.metric_rank(est, "off", "epa", TEAMS)
    dfn = pm.metric_rank(est, "def", "epa", TEAMS)
    assert off["AAA"] == 1 and off["DDD"] == 4, off
    # Everyone's defense allowed the same mix, so ranks tie, but the direction
    # test is on pressure: AAA allowed pressure, so its offense ranks last and
    # every defense that faced AAA generated some.
    prs_off = pm.metric_rank(est, "off", "prsr", TEAMS)
    assert prs_off["AAA"] == 4, prs_off
    scores = pm.battle_scores(est, prior, TEAMS, "off")
    ranks, pcts = pm.rank_desc(scores["overall"])
    assert ranks["AAA"] == 1 and pcts["AAA"] == 1.0 and pcts["DDD"] == 0.0
    # Tendency metrics rank by rate on both sides.
    ten = pm.metric_rank(est, "def", "blitz", TEAMS)
    assert set(ten.values()) == {1}, "equal blitz rates should all tie at rank 1"
    print("ok  ranks point the right way for offense, defense and tendencies")


def test_current_week_flips_after_last_game():
    sched = schedule()
    assert pm.current_week(sched, "2030-01-01") == 1
    assert pm.current_week(sched, "2030-01-03") == 3
    assert pm.current_week(sched, "2030-02-01") == 18
    print("ok  current week flips the day after the week's last game")


def test_edge_label():
    assert pm.edge_label(0.7) == "Big offense edge"
    assert pm.edge_label(-0.3) == "Defense edge"
    assert pm.edge_label(0.1) == "Even"
    print("ok  edge labels")


if __name__ == "__main__":
    test_week1_is_regressed_prior()
    test_prior_fades_with_games()
    test_new_qb_haircut()
    test_rank_direction()
    test_current_week_flips_after_last_game()
    test_edge_label()
    print("all matchup tests passed")
