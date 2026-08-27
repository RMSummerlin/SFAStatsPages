# Pace data decisions

How the pace numbers are built, and why they are built that way. Companion to
`docs/personnel-grouping-data.md`. Every figure quoted below comes from the 2025
sheet: 33,327 rows, 272 games, 5,696 drives.

## Tempo is play clock used, not snap-to-snap

**Play clock used = 40 − seconds left on the play clock at the snap.** It answers
"how much of their allowance did this offense burn before snapping."

The obvious alternative, `TimeSinceSnap`, is real-world seconds between
consecutive snaps. It was the original metric here and it is worse, because it
bundles two unrelated things:

```
TimeSinceSnap  =  how long the previous play took to finish
               +  how long the offense then took to snap
```

Only the second term is a tempo decision. The first is a play-outcome artifact —
a 40-yard completion takes longer to whistle dead than a two-yard run, so an
explosive offense looks slow for reasons that have nothing to do with tempo.
Play clock used drops that term entirely.

The data agrees. Splitting the season into odd and even weeks and correlating
each team's neutral figure across the two halves:

| Metric | Team SD | Range | Split-half r | Full-season r |
|---|---|---|---|---|
| Snap-to-snap seconds | 1.13 | 5.19 | 0.74 | 0.85 |
| **Play clock used** | 1.15 | 5.40 | **0.86** | **0.93** |

Same spread, materially more signal. The two rank teams almost identically
(r = 0.957), so this is a cleaner measurement of the same thing rather than a
different statistic.

Two practical bonuses: it is bounded 0–40 by construction, so nothing needs
winsorizing (snap-to-snap ran to 75 seconds and had to be clipped at 60), and
"they used 33 of their 40 seconds" is a sentence a reader understands without a
glossary.

### The 40-second gate

Play clock used is only comparable when the play clock actually started at 40.
The NFL resets to **25** after a change of possession, timeout, penalty, injury,
measurement, replay review, the two-minute warning and the start of a period.
Counting those as 40 would credit an offense with roughly fifteen seconds it
never had.

`TimeSinceSnap` turns out to be an almost exact indicator of that set — it is
blank on 96% of first-plays-of-drive and 94% of post-timeout snaps. So it stops
being the metric and becomes the gate: **a play contributes to tempo only if it
has a `TimeSinceSnap`.** That selects the 40-second universe without this
codebase having to encode the rule book.

Verified directly:

- First plays of drives (5,692 of them) top out at **25** on the play clock, with
  4 exceptions. Sharp cliff, exactly where the rule says it should be.
- Plays with `TimeSinceSnap` present reach **39**, and 2.6% of them exceed 25 —
  impossible on a 25-second clock.
- Summing `TimeSinceSnap + PlayClock` on ordinary plays clusters tightly at
  45–47: about six seconds for the play itself, then a 40-second clock running
  down. Confirms the 40 directly rather than by assumption.

**Penalties are the exception the gate misses.** Those snaps keep a
`TimeSinceSnap` but run on 25 seconds, and their play clock maxes at exactly 25
across all 260 of them in 2025, against a mean `TimeSinceSnap + PlayClock` of
71.9 rather than 47. They are excluded explicitly, using the penalty yardage
columns with the play description as a backstop.

Net: about 23,600 of 32,800 plays carry a tempo figure. The rest still count
toward every volume metric.

## Play ordering: use PlayId, never file order

`PlayId` is a per-game sequence that spans **both** offences. `(GameId, PlayId)`
is unique across every row.

The sheet is grouped by team, not by time. In the 2025 opener, Buffalo's first
drive occupies rows 0–6 and Baltimore's reply sits at row 7,344. **Zero of the
272 games have monotonic `PlayId` in file order.**

This is no longer hypothetical. Excluding the snap *after* a penalty requires
knowing which play came before, so `mark_prior_penalties()` sorts on
`(GameId, PlayId)` before walking the rows. Done on file order it would attribute
penalties across the wrong team's drives.

## Neutral, trailing, and the two-minute windows

**Neutral** — quarters 1 to 3, margin within 14 points either way, excluding the
final two minutes of the half. About 15,100 plays league-wide, ~470 per team.

**Trailing** — margin of 5 or more points behind, excluding the final two
minutes of either half. About 7,400 plays, minimum 113 for any single team.

**Gear change** — neutral minus trailing. Positive means the offence speeds up
when it falls behind.

### Why trailing by 5 and not by two scores

Two scores (9+) is the more intuitive definition and it produces a wider spread,
so it was the first choice. It does not survive testing. Splitting each season
into odd and even weeks and correlating a team's gear change across the two
halves:

| Trailing bucket | Split-half r | Full-season r (Spearman-Brown) | Teams under 75 plays |
|---|---|---|---|
| Trailing 5+ | 0.41 | **0.58** | 0 |
| Trailing 9+ | 0.38 | **0.55** | 5 |

(Figures on play clock used. On snap-to-snap the gap was much wider — 0.61
against 0.29 — so the cleaner metric narrows it, but 5+ still wins on both
reliability and coverage.)

Most of the extra spread in the two-score version is sampling noise: a team's
gear change over the first half of the season barely predicts its own gear change
over the second half. Trailing 5+ is both more reliable and gives every team a
number.

For reference, neutral play clock used itself splits at **r = 0.93**. That column
is very solid.

### Minimum plays

Any split needs 75 plays before a number is shown; below that the cell is a dash.
This never binds at season level — the thinnest 2025 team has 113 trailing plays
and 366 neutral — so it only takes effect once a filter narrows the sample. A
single team-game averages only about 28 neutral plays, which is nowhere near
enough to rank.

## No win probability model

Considered and rejected. Tempo intent responds to essentially two inputs: whether
you are behind, and whether the clock is about to matter. A win probability model
adds field position, timeouts, down and distance, and the betting line — none of
which meaningfully changes a coordinator's tempo decision, all of which add a
black box that a reader cannot audit. The betting line is not in the sheet
anyway.

Excluding the two clock-strategy windows and bucketing on margin gets the same
answer, is reproducible by a sceptical reader from the sheet alone, and fits in
one sentence of tool copy.

## Opponent adjustment: for volume, not for tempo

The sheet has `opponent` on every row, so adjustment is cheap either way. It is
only worth doing for one of the two.

**Tempo — not adjusted.** Defenses vary in the pace they face by only 0.47s
standard deviation, and averaged over a 17-game schedule that collapses to
**0.13s SD with a 0.61s total range across all 32 teams**. Against a team spread
of about 5.4 seconds, adjustment reproduces the unadjusted column with a decimal
wobble. An adjusted column here would imply a precision the data does not have.

**Plays per game — adjusted.** Defences vary in plays allowed by 2.21 SD across
a 9.1-play range, and schedule strength is 0.41 SD / 1.65 range. Applying it
moves Denver from 5th to 1st, Chicago 1st to 4th, LA Chargers 3rd to 6th — up to
four rank positions. That is a real column.

The adjustment is a single pass: a defence's baseline is its plays allowed per
game, a team's expectation is the mean baseline of the defences it faced, and the
adjusted figure is `raw − expected + league mean`. No iteration, no ridge. Given
the size of the effect, anything more elaborate would be false precision.

## Volume is not tempo

Worth stating plainly because readers will assume otherwise. Plays per game
decomposes into drives per game times plays per drive, and **plays per drive
correlates with tempo at about −0.17** — essentially nothing.

Cleveland runs among the league's shortest drives (160s, 5.48 plays) while
sitting mid-pack in actual tempo. Buffalo has the longest drives (206s, 6.53
plays) and is one of the *slowest* teams, using 33.5 of its 40 seconds.

This is why the tool splits Tempo and Volume behind a mode toggle rather than
laying all nine columns in one table. Side by side they read as nine measures of
the same thing, and they are not.

## Drive metrics

`DriveStartClock` and `DriveEndClock` each count down inside their own quarter,
so a drive that crosses a quarter boundary has an **end clock larger than its
start clock**. Subtracting naively yields a negative duration that then quietly
drags time of possession down. The correct form is:

```
duration = start − end                     if end ≤ start
duration = start + (900 − end)             if end > start
```

Applied across 2025: 5,696 drives, zero negative, zero longer than a quarter.
Pinned by `scripts/test_pace.py`.

Two exclusions:

- Drives with result `End of Half` or `End of Game` are excluded from duration
  and time of possession — their length reflects when the half started, not how
  the offence operated. They still count toward plays per drive.
- Drives consisting only of kneels disappear entirely, since every one of their
  plays is filtered out. That accounts for the gap between 5,696 raw drives and
  the 5,518 in the payload.

**Do not use the `DrivePlays` column.** It counts field goal attempts as a play
but does not count punts, so it runs one high on field goal drives and exactly
right on punts. The script counts surviving rows instead.

## Special teams are absent

`PlayType` only ever holds `PASS` or `RUSH`, so punts, field goals and kickoffs
have no rows. Consequences:

- Plays per game means *offensive scrimmage plays* per game.
- Drive start field position is available via `DriveStartDist`, but the kickoff
  or punt that produced it is not.

If special teams rows are ever added to the export, plays per drive and time of
possession get more accurate and drive-level content opens up considerably.

## Columns read

Required, and the pull fails loudly without them:

```
team, opponent, week, qtr, down, PlayType, PlayDesc, ScoreDiff, DriveNumber
```

Optional. A season missing these is still published, with the affected metrics
switched off and a warning in the Actions log:

```
TimeSinceSnap, PlayClock, Huddle, HomeRoad, GameClock, GameId, PlayId,
DriveStartClock, DriveEndClock, DriveResult, OffPenaltyYds, DefPenaltyYds
```

Tempo needs **both** `PlayClock` and `TimeSinceSnap` — one supplies the number,
the other decides which plays it applies to. A season with only one of them
publishes as a volume-only season.

That split is deliberate. Rather than checking by hand which historical sheets
carry the pace columns, run the workflow with **Rebuild every season** ticked and
read the log: every season missing them prints a warning and is left out of
`pace_index.json`, so the tool only offers seasons that will actually render.

## Neutral pass rate

Added because passing and pace feel related. The relationship is real, but it is
not the one it is usually described as.

**Correlation with tempo is nil.** Neutral pass rate against neutral play clock
used: **−0.033**. Against snap-to-snap seconds, in case the older metric was
hiding it: **+0.015**. Both are zero. Pass-heavy offenses do not get to the line
faster.

**Correlation with volume is real.** Against plays per game: **+0.31**. That is
the actual mechanism — incompletions and sideline throws stop the clock, so
passing buys extra snaps. It drives *how many* plays, not *how quickly* they are
run. Anyone reading the column as a tempo indicator will draw the wrong
conclusion, so its tooltip says so outright.

It is worth having: signal SD 3.02 percentage points against binomial noise of
2.01, and a 15-point spread from Arizona at 65.3% down to the Jets at 49.9%.

### Dropbacks, not PlayType

Pass rate here counts **dropbacks**. Sacks already arrive as `PlayType = PASS`,
which is right — the play call was a pass. Scrambles arrive as `RUSH` even though
they were also called passes, so they are folded back in.

Not a cosmetic choice. There were 1,102 scrambles in 2025, and switching
definitions moves teams by up to **eleven rank positions** — Kansas City reads
56.5% on `PlayType` alone and 63.1% counting scrambles, the Jets 44.3% against
49.9%. `PlayType` alone measures quarterback mobility as much as play calling.

### A wider denominator than the column beside it

Pass rate needs no 40-second play clock, so its denominator is **every** neutral
play, not only the tempo-eligible ones: about 19,400 rather than 14,900 in 2025.
The two neighbouring columns deliberately rest on different bases, which is why
`test_pace.py` pins pass rate against a fixture whose `TimeSinceSnap` is blank
throughout.

## Passing gear change: measured and rejected

The natural companion — how much more a team passes when trailing — was tested
and is not a real team trait at single-season sample sizes.

| | Value |
|---|---|
| League mean shift when trailing by 5+ | **+8.3 points** |
| Observed spread between teams | 3.69 pp SD |
| Spread expected from sampling noise alone | 3.58 pp SD |
| Implied signal | 0.91 pp |
| Odd/even week split-half r | **0.00** |

Every team passes far more when behind, and the *differences* between teams are
very nearly all noise: a team's first-half-of-season figure carries no
information about its second half. The column would rank 32 teams on a coin
flip, and the ordering would look plausible enough that nobody would notice.

More seasons would not rescue it. A split-half of zero says the signal is absent
rather than merely under-sampled, so pooling years would shrink every team toward
+8.3 rather than resolve differences between them.

Not the same conclusion as the tempo gear change, which survived the same test at
r = 0.58 and is in the tool.

## Pooling seasons

The tool's season control is multi-select, so all the aggregation runs over
whatever set of seasons is chosen. Two consequences worth knowing:

**Team identity is by code, not by position.** Each payload indexes its own teams,
and pooling maps every season's local index into one shared registry keyed on the
abbreviation. That makes the abbreviation the franchise's identity, so anything
that changes it splits a franchise in two.

`TEAM_ALIASES` in `pull_pace.py` folds those together before publishing, always
toward the franchise's **current** code so history collapses into the present
rather than the present being renamed into history:

| Fold | Reason |
|---|---|
| `WFT`, `WSH` → `WAS` | Football Team, 2020–21 |
| `OAK`, `LVR`, `RAI` → `LV` | Oakland → Las Vegas, 2020 |
| `SD`, `SDG` → `LAC` | San Diego → Los Angeles, 2017 |
| `STL`, `SL`, `LA`, `RAM` → `LAR` | St. Louis → Los Angeles, 2016 |
| `JAC`, `ARZ`, `BLT`, `CLV`, `HST`, `KAN`, `NOR`, `SFO`, `GNB`, `NWE`, `TAM` | Provider house style |

Verified end to end by relabelling every Washington row in the real 2025 export
as `WFT`, building it as a second season and pooling the two: 32 teams, one
Washington row, and the fold reported in the log.

Two guards, because a missed alias is silent rather than loud — it just adds a
33rd row that looks plausible:

- Every fold is counted and printed: `2021: pooled WFT → WAS (2,040 team-play
  references)`.
- Any season that does not resolve to exactly 32 teams prints its full team list
  and points at `TEAM_ALIASES`.
- `test_pace.py` asserts no alias needs two hops, since `canonical_team` does a
  single lookup and a chain like `A → B → C` would quietly leave rows under `B`.

Normalising here rather than in the tool keeps the JSON, the crawlable preload
table and the browser in agreement.

**Opponent adjustment pools its baseline too.** Across a multi-season selection,
a defense's plays-allowed baseline is computed over the whole span rather than
per season and then averaged. That is the right question for a multi-year view —
how did this offense compare to everything it actually played — but it is not
identical to averaging per-season adjustments, and it drifts slightly if
league-wide play volume has moved over the span. For single-season views, which
is the default, the two are the same thing.

## Known oddity: Washington's no-huddle rate

Washington charts at **60.8% no-huddle** against a 9.9% league average — a six-fold
outlier, and more than double the next team (New Orleans, 23%). It is identical in
both sheet exports, so it is not an export bug, and a Kingsbury offense running
heavy tempo is a plausible explanation. But a single team sitting that far outside
the distribution is also exactly what a mid-season charting definition change
looks like. Worth checking against a second source before leaning on the
no-huddle column in written analysis.
