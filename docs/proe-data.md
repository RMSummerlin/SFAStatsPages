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

Two consequences worth stating plainly:

- **The league mean is not zero.** The league has leaned further toward the
  run across 2021–2025 than the pool's average, so a typical 2025 or 2026
  offense reads about one point negative. The public nflfastR tables show the
  same effect at about two points, because their model was fit on 2006–2019.
- **The 2026 numbers will shift once, by a fraction of a point,** when 2026
  completes and joins the pool. Nothing else about a finished season changes.

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

2026 through week 3 against nfelo's published table, which runs on nflfastR:
r = 0.94 across 32 teams, mean gap 1.7 points, same top team (Dallas) and
bottom team (Atlanta). The larger gap early in a season is sample size on both
sides, not method.

## What is published

`data/proe_<season>.json` carries, per team and week, seven numbers:
dropbacks, expected dropbacks and plays for the offense, the same three for
the defense it faced, and the opponent. Everything in the tool is a sum of
those: the season figure, the week range, the last four games, the per-week
chart and the pooled multi-season view. No play-level data ships, because no
filter in this tool needs it.

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
  footer row is the league mean rather than a target.
- **Matchups add the two sides.** An offense at +4 against a defense whose
  opponents sit at +3 projects to about +7. That is the lean the track draws,
  against a full-track value of 15 points, with both inputs printed at the
  ends. Figures are always season to date; past weeks are not snapshotted,
  because the point of the tab is to pair this week's games with what the
  two units are now.
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
