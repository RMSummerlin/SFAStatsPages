# Weekly Matchups: data decisions

What the tool measures, how the blend works, what the backtest found, and where
the numbers come from. Read this before changing `scripts/pull_matchup.py`.

## What it shows

One game at a time, two halves: away offense vs home defense and home offense vs
away defense. Five battle rows per half, each an offense rank against a defense
rank with the gap between their percentiles drawn as an edge:

| Battle | Offense metric | Defense metric | Built from |
|---|---|---|---|
| Overall | 0.6 z(success rate) + 0.4 z(EPA/play) | same, allowed | all pass and rush plays |
| Passing | same on dropbacks | same, allowed | PASS plays plus scrambles |
| Rushing | same on designed runs | same, allowed | RUSH plays minus scrambles |
| Pressure | pressure rate allowed (lower better) | pressure rate generated | `PFFPrsrAlwd == Yes` over dropbacks |
| Explosives | explosive play rate | explosive rate allowed | pass 15+ or rush 10+ yards |

z is standard deviations from the prior season's league mean using the prior
season's team-level spread. Success rate carries more weight than EPA because it
was the more stable input (below). Kneels and spikes are excluded with the same
word-bounded regex the other pulls use.

Every metric is mirrored for free: each play is credited to the offense that
ran it and to the defense that faced it.

Pop-out splits (blitz, man/zone, play action, deep targets, yards before and
after contact, sacks, time to throw, early downs, third downs, explosive pass
and rush) use the same blend with larger prior weights, are not
opponent-adjusted, and show a dash below 40 plays this season.

## The blend

For as-of week W, a unit's rating on metric m is

    ( sum over games t < W of w_t * (num_t - adj_t * den_t)  +  Kp * prior_value )
    / ( sum of w_t * den_t  +  Kp )

* `w_t = 0.5 ** ((W - t) / H)`, H = 10 games
* `Kp = K * average_den_per_game * 0.5 ** (W / H)`: last season is one
  pseudo-observation at week 0 worth K games, fading on the same clock
* `prior_value = league_mean + r * (team_last_season - league_mean)`
* `adj_t` = the opponent's rating on the same metric minus the league mean, so
  facing a top defense stops counting against an offense. Solved iteratively
  with both sides together, three passes. Battle metrics only.

Parameters (K games, r) by side:

| Metric | Offense | Defense |
|---|---|---|
| Success rate, dropback success | 8, 0.5 | 14, 0.2 |
| EPA/play | 8, 0.4 | 14, 0.2 |
| EPA/dropback | 10, 0.4 | 14, 0.2 |
| Rush SR, rush EPA | 12, 0.3 | 14, 0.2 to 0.3 |
| Pressure rate | 10, 0.4 | 10, 0.2 |
| Explosive rate | 12, 0.3 | 10, 0.2 |

Resulting prior share of a headline offense rating: 100% at week 1, about 88%
at week 2, 70% at week 4, 56% at week 6, 38% at week 10, 27% at week 14. Defense
(K=14) stays above 50% through week 10. Multiply by r for last season's actual
influence; the rest of the prior is shrinkage toward league average, which is
most of what it does.

Snapshots are as-of. The card for week W reads games with week < W only, and
never changes once week W is in, so the week stepper shows what was known at the
time. The latest snapshot ships in full inside `matchup_<season>.json`; older
weeks keep only their battle scores there and fetch `matchup_<season>_w<W>.json`
for the pop-out.

## Backtest

Four season pairs, 2021 to 2025, 128 team-seasons, scored by RMSE against each
unit's actual rest-of-season rate (at least four games remaining). Reproduced by
`backtest_matchup.py` in the analysis notes, not in this repo, since it needs
pandas and is not a pipeline script.

**Half-life does not matter.** Above about six games every H scored the same,
and H = infinity (plain season-to-date) was within noise of the best. Short
half-lives (2 to 4) were strictly worse, including for next-game prediction and
for weeks 10 to 18 only. The tool uses H = 10 for a light recency lean; it is
not a feature and the copy does not sell it.

**Last season matters longer and less than intuition.** Best K was 8 to 14
games with heavy regression: r = 0.3 to 0.5 on offense, 0.2 on defense. A raw
last-season rating (r = 1) was worse than the league mean by week 3.

**Year-over-year retention and split-half stability:**

| Metric | Off YoY | Def YoY | Off split-half | Def split-half |
|---|---|---|---|---|
| EPA/play | 0.39 | 0.23 | 0.55 | 0.31 |
| Success rate | 0.47 | 0.27 | 0.58 | 0.33 |
| Dropback EPA | 0.43 | 0.11 | 0.50 | 0.23 |
| Rush EPA | 0.21 | 0.22 | 0.28 | 0.15 |
| Pressure rate | 0.34 | 0.40 | 0.56 | 0.42 |
| Explosive rate | 0.30 | 0.20 | 0.47 | 0.33 |

**Defense is close to unpredictable; rushing is worse.** Out-of-sample R² of
the best blend against rest-of-season: offense EPA 0.11 at week 1 rising to
0.35 by week 12; defense EPA never above 0.11; pass defense EPA at most 0.06;
rush EPA either side at most 0.10 and 0.01 to 0.06 through week 6. Pressure
rate is the exception (offense 0.39, defense 0.18).

Consequences in the tool: defense is shrunk harder so its ranks bunch toward the
middle early, and the edge is driven more by the offense than the defense. That
is the honest reading. The Rushing row stays because readers expect it, but its
fill stays faded longer and the pop-out shows the sample.

**A new QB1 halves the prior's usefulness.** Teams with a new primary passer:
year-over-year correlation 0.16 vs 0.37 (EPA), 0.31 vs 0.46 (SR). Hence
`QB_NEW_K_SCALE = 0.5` and `QB_NEW_R = 0.2`. The coordinator haircut
(`COACH_NEW_R_SCALE = 0.75`) was not tested and is a judgment call.

**Opponent adjustment did not help in the backtest.** A one-pass version made
offense slightly worse and defense marginally better. It is in the tool because
early-season schedules are unbalanced and the editorial decision was to
schedule-adjust; the effect on accuracy is roughly zero either way.

## Inputs beyond the sheets

**Schedule:** nflverse `games.csv`, fetched every run and cached to
`data/schedule_<season>.json`. Provides kickoff, home/away, neutral site,
stadium, scores once played, and each game's listed starting QB. If the fetch
fails the cached copy is used; with neither, the season is skipped and the last
published files stand. The current week is the first week with a game dated
today or later, so it flips the day after MNF.

**Offseason changes:** `data/offseason_changes_<season>.json`, drafted by
`scripts/offseason_changes.py` (QB1 from nflverse week 1 starters against the
prior season's most common starter; HC, OC and DC from the Wikipedia coordinator
navbox revisions before and after the offseason) and corrected by hand. The
pull trusts the file. A mid-season QB change is detected from the schedule: if
this week's listed starter is not the one who opened the season, the offense
gets the QB haircut and the card shows "New since wk N".

**Rams code:** the 2021 to 2024 sheets and nflverse use `LA`; the 2025 sheet
uses `LAR`. `config.canonical_team` folds both.

## Things that look like bugs but are not

* Week 1 defensive ranks are nearly all of the same color and the top defense
  ranks 1st by a hair. Expected: r = 0.2 on defense means last season's best
  defense is projected barely above average.
* A team's rank moves between the week 3 card and the week 4 card without
  playing. The week 4 card includes week 3 games for everyone else, and the
  opponent adjustment re-solves.
* The mismatch number in the picker can be high for a game with no big single
  edge; it is the sum of ten absolute edges.
* "New QB" on a team whose week 1 starter was the plan all along. The changes
  file compares against the prior season's most common starter, so a rookie or
  a free agent who started week 1 is new by that definition.
* A split shows a dash while its rank is not blank. The dash is the 40-play
  gate; the rank is on the blended value, which exists.
