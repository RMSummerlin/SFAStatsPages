# Pass rate over expected: data decisions

How the PROE numbers are built, why they are built that way, and how they
compare with the model everyone else publishes. Companion to
`docs/pace-data.md` and `docs/metric-definitions.md`. Figures quoted below
come from a local run of `scripts/pull_proe.py` over nflverse play-by-play
for 2021 to 2025 reshaped into the sheet's columns, which is the same play
set the sheets carry to within two plays a season, and from the 2026 export
through week 3.

## The metric

A team's PROE is its dropback rate minus the dropback rate a typical team
would have had in the same situations, in percentage points, over whatever
plays are in view. Per play:

```
over expected = dropback (0 or 1) − expected dropback probability
PROE          = 100 × mean(over expected)
```

A dropback is `PlayType = PASS` (sacks already arrive that way) or a scramble
(`PlayType = RUSH` with `Scramble?` set). Same definition as the pace tool's
neutral pass rate, for the same reason: it tracks the call, not the outcome.
Kneels and spikes are excluded.

The defense's figure is the same sum over the plays it faced. A defense with
+3 sees opponents call passes 3 points more often than the situations
warranted. Nothing is opponent-adjusted on either side.

## The expectation: league rate by situation bucket

The public version of this metric (nflfastR's `xpass`, which Establish The
Run, rbsdm, nfelo and the rest republish) is an XGBoost model with 17 inputs
including the betting line and win probability. The sheet has no betting line,
no timeouts per play and no roof type, and this repo's standing rule, set when
the pace tool rejected a win probability model, is that a reader should be
able to rebuild any published number from the sheet alone. So the expectation
is a **lookup**: the league's dropback rate in the play's situation bucket.

Five fields, each cut into bands:

| Field | Bands | Code |
|---|---|---|
| Down | 1, 2, 3, 4 | `1`–`4` |
| Distance | 1 · 2–3 · 4–6 · 7–9 · 10 · 11+ | `d1 d2 d4 d7 d10 d11` |
| Field zone (`los`, yards to the goal line) | own 1–20 · own 21–50 · opp 49–21 · red zone | `A B C D` |
| Clock state | Q1–Q2 outside the last two minutes · Q2 last two minutes · Q3 · Q4 outside the last four · Q4 last four and overtime | `h1 h1l q3 q4 late` |
| Score margin | ≤ −17 · −16 to −9 · −8 to −4 · −3 to +3 · +4 to +8 · +9 to +16 · ≥ +17 | `m3 m2 m1 e p1 p2 p3` |

The full key has 3,360 possible cells. 2,595 occur in 2021–2025 and 328 hold
100 or more plays. Those 328 cover about two thirds of all plays; the rest
fall back.

### Thin buckets fall back

A bucket with fewer than `MIN_BUCKET = 100` plays defers to the first coarser
key that has enough, in this order:

| Tier | Keeps | Share of plays, 2025 |
|---|---|---|
| 0 | down, distance, zone, clock, margin | 67.9% |
| 1 | down, distance, clock, margin | 21.6% |
| 2 | down, clock, margin | 9.8% |
| 3 | down, clock | 0.6% |
| 4 | down | 0 |

Field zone goes first because it moves pass rate least once down and distance
are known. Clock state goes last because the two-minute and four-minute
windows are the situations where nothing else predicts the call. 100 plays
puts the standard error of a bucket's rate under five points, which is the
scale of the differences between teams. Every play's expected rate is taken
from the finest key the league has actually populated.

### Which seasons build the baseline

**Every completed season in `scripts/config.py`.** The season in progress is
measured against that fixed pool, so a team's number only moves when it
plays, never because the baseline drifted under it. Each completed season sits
inside the pool it is compared with: the question is how an offense called
plays against the league of its era, not against one year's fashion.

The pool is cached in `data/proe_baseline.json` as per-season bucket counts.
A scheduled run reads only the current season's sheet and sums the cache. When
the cache does not hold exactly the completed seasons (first run, or a season
rolled over), the pull re-reads every sheet and republishes every season, so
the rollover needs no manual step beyond adding the new sheet to config.

### Displayed figures are centred on the season's league

The pool is more pass-happy than the league has been since, so a typical 2025
or 2026 offense measured against it reads about one point negative. Left
alone, that would put every team a point or two below the tables readers
compare against (Fantasy Points centres near zero; StatRankings sits at
−0.2; the raw nflfastR tables at −2 because their model was fit on 2006 to
2019). So every figure the tool shows subtracts the league's over-expected
rate for that season on the plays in view, in the browser, before anything is
summed or pooled:

```
offset_season = (Σ dropbacks − Σ expected) / Σ plays      over every team's plays in view
team PROE     = 100 × Σ (dropbacks − expected − offset × plays) / Σ plays
```

The same offset applies to the offense and the defense side, since both sums
cover the same plays, and the preload table does the same subtraction in
`summarise()`. The NFL Average row therefore reads 0.0 by construction on the
PROE column. A multi-season view centres each year on its own league before
pooling, so a +3 always means three points above that season's league.

What this costs: a team's number can move by a tenth or two when other teams
play, because the league mean moved, and the drift of the league itself is no
longer in the figures. That drift is one sentence of page copy, so it was the
cheaper thing to lose. The uncentred figure is recoverable from the published
file for anyone who wants it, since the file carries the raw sums.

The validation below compares the uncentred figures, which is the like-for-like
comparison with nflfastR's `pass_oe`; centring moves every team by the same
constant within a season, so correlations and rank gaps are unchanged.

## Validation against nflfastR

The real test is whether a lookup table reproduces the model. Team PROE from
this script against the mean of nflfastR's own `pass_oe` over the same plays:

| Season | r | Mean abs gap (pts) | Largest rank gap | League mean, ours / nflfastR | Split-half r, ours / nflfastR |
|---|---|---|---|---|---|
| 2021 | 0.986 | 1.11 | 4 | −0.11 / −1.15 | 0.70 / 0.71 |
| 2022 | 0.994 | 1.14 | 6 | −1.42 / −2.54 | 0.84 / 0.83 |
| 2023 | 0.986 | 1.33 | 6 | −0.26 / −1.57 | 0.75 / 0.80 |
| 2024 | 0.991 | 1.23 | 6 | −1.04 / −2.28 | 0.77 / 0.79 |
| 2025 | 0.983 | 1.22 | 4 | −1.08 / −2.28 | 0.58 / 0.60 |

Read across: the two rank teams almost identically, the gap is about a point
and is mostly the baseline offset, and the lookup is as reliable from one half
of a season to the other as the model is. The 2025 top five are the same five
teams in both (Kansas City, Arizona, the Rams, New England, Denver in ours;
Arizona, Kansas City, the Rams, New England and Atlanta then Denver in
nflfastR's), and the bottom three are the same three.

### Early-season agreement is looser, and that is sample size

2026 through week 3, our method on the sheet against four published tables
that all run on nflfastR's model (nfelo, muffed, Dynatyze and StatRankings):
r = 0.93 to 0.94 across 32 teams, mean gap 1.5 to 1.8 points, same top
team (Dallas) and bottom team (Atlanta). The same comparison over a full
season sits at r = 0.98 to 0.99 with a 1.2-point gap, so the extra
disagreement at three games is noise on about 180 plays a team, not a
different answer.

Three checks behind that reading:

- **It is not the data.** The sheet and nflverse carry the identical 5,814
  plays through week 3, with the same dropback rate for every team. Our
  method on the nflverse rows reproduces our method on the sheet at
  r = 0.999.
- **It is not the betting line.** Adding a pre-game spread band to the bucket
  key (favored by 7+, 3 to 6.5, pick, dog by 3 to 6.5, dog by 7+, from the
  nflverse schedule) moves the full-season agreement from 0.986 to 0.992 in
  the best year and leaves 2026 unchanged at 0.943. Not worth a sixth field
  and a second data source.
- **Per play, the two expectations agree.** Our bucket rate against
  nflfastR's `xpass` on the same play: r = 0.88, mean gap 0.07. The largest
  systematic differences are a few cells in the fourth quarter and the last
  two minutes of the half, where ours expects three to six points less
  passing because the 2021 to 2025 pool is more run-heavy than the model's
  2006 to 2019 training years.

What this means in practice: through the first month a team can sit two to
three points, and a few rank positions, from a public nflfastR table. By
midseason the two tables agree to the decimal on most teams.

## What is published

`data/proe_<season>.json` carries, per team and week, seven numbers:
dropbacks, expected dropbacks and plays for the offense, the same three for
the defense it faced, and the opponent. Everything in the tool is a sum of
those: the season figure, the week range, the last four games, the per-week
chart and the pooled multi-season view.

For the quarter and down filters the file also carries `twq`: the offense's
three numbers per team and week split by quarter (5 is overtime) and down, as
`[quarter, down, dropbacks, expected, plays]` cells. Only the offense is
split, because a defense's plays in a week are exactly the plays of the
offense it faced, so the tool reads the opponent's cells through the opponent
code the team-week already carries. The split cells add back to the team-week
counts exactly; expected dropbacks are rounded per cell, so under a filter
that happens to keep every cell the figure can sit a hundredth of a point
from the unfiltered one, which is why the tool reads the plain sums whenever
no quarter or down is picked. `schema` is 2 with the split; the pull rebuilds
every season once when it finds an older file. No play-level data ships.

Also in the file: the schedule with scores (from the nflverse `games.csv`
cache the matchup tool already keeps), each team's bye week derived from the
weeks it is absent, the current week (first week with an unplayed game, so it
flips the day after Monday night), and the baseline's season list and play
count for the footer.

## Decisions in the tool

- **Last 4** is the team's last four played games in the newest selected
  season, inside the week range. Early in a season it reads what there is,
  so it equals PROE until week 5. Establish The Run publishes the same split
  and uses it to catch play-caller changes.
- **Rank 1 is the most pass-heavy** on both tabs. PROE is a tendency, so the
  shading is diverging on value, teal above zero and red below, and the
  footer row is the play-weighted league figure, 0.0 on PROE by construction.
- **Matchups add the two sides.** An offense at +4 against a defense whose
  opponents sit at +3 projects to about +7. The tab is one table for the
  week, a row per offense against the defense it faces, sorted on that sum
  by default and sortable on either input, so a 32-row week ranks every unit
  pairing at once. Figures are always season to date and never narrowed by
  quarter or down; past weeks are not snapshotted, because the point of the
  tab is to pair this week's games with what the two units are now.
- **Quarter and down narrow everything on the team tabs,** and the league
  centring is recomputed on the narrowed plays, so the NFL Average row reads
  0.0 under any filter. A fourth-quarter figure therefore says how a team
  calls the fourth quarter relative to how the league calls it, not relative
  to the league's whole game.
- **Pooled seasons** sum the team-week cells across the chosen years, as the
  pace tool does. The expansion shows one 18-week chart per season rather
  than one blended line, because the chart's job is to show the shape of a
  season.

## Columns read

Required, and the pull fails loudly without them:

```
team, opponent, week, qtr, down, dist, los, GameClock, ScoreDiff, PlayType, PlayDesc
```

Optional: `Scramble?` (without it scrambles count as runs and the pull warns;
every sheet since 2021 has it), `GameId`, `PlayId`, `HomeRoad`.
