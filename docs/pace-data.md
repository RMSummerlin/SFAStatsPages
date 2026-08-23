# Pace data decisions

How the pace numbers are built, and why they are built that way. Companion to
`docs/personnel-grouping-data.md`. Every figure quoted below comes from the 2025
sheet: 33,327 rows, 272 games, 5,696 drives.

## TimeSinceSnap is the whole tool

Column `TimeSinceSnap` is **real-world seconds between consecutive snaps**, not
game-clock elapsed time. That distinction is the single most important thing to
understand before touching this pipeline.

Verified two ways against the game clock:

- On plays where the clock ran continuously between snaps, `TimeSinceSnap`
  matches the game-clock delta **exactly on 91% of plays**, median difference
  zero seconds.
- On plays following an incompletion, the game clock burned an average of
  **5.5 seconds** but `TimeSinceSnap` reads **43.2**. It is tracking the huddle
  and the play clock, not the scoreboard.

This matters because the naive way to measure pace — subtract consecutive game
clocks — makes any pass-heavy offence look breathlessly fast, since an
incompletion stops the clock. Every play after an incompletion would score about
five seconds. `TimeSinceSnap` sidesteps that entirely.

### The blanks are the feature

`TimeSinceSnap` is empty on 27% of rows. That is correct and deliberate on the
provider's side, not missing data:

- 96% of first-plays-of-drive (there is no previous snap to measure from)
- 94% of snaps following a timeout
- Snaps following injuries, measurements, replay reviews and the two-minute warning

Those are exactly the gaps that would otherwise need hand-built exclusion rules,
and they are already removed upstream. **The pull script therefore does no
clock-state filtering of its own.** If you find yourself writing one, check
whether `TimeSinceSnap` already handled it.

Blank rows are still kept in the payload — they count toward plays per game and
plays per drive, and are skipped only for tempo. A blank is encoded as `0`, which
is free as a sentinel because real values start at 1.

### Winsorized at 60 seconds

The raw column tops out at 75. There are 913 plays at 60 or above and 231 at 70
or above, and they are overwhelmingly unflagged penalty administration rather
than a genuinely slow offence. Left alone, a handful of 70-second plays visibly
drags a team's mean. Values above 60 are clamped to 60 and the count is reported
in the pull log and in the payload as `tss_capped` (844 for 2025).

## Play ordering: use PlayId, never file order

`PlayId` is a per-game sequence that spans **both** offences. `(GameId, PlayId)`
is unique across every row.

The sheet is grouped by team, not by time. In the 2025 opener, Buffalo's first
drive occupies rows 0–6 and Baltimore's reply sits at row 7,344. **Zero of the
272 games have monotonic `PlayId` in file order.**

Nothing in the current metric set depends on play ordering, because
`TimeSinceSnap` arrives pre-computed. The script sorts by `(week, PlayId)`
anyway, so that any future metric which does need sequence is correct by
construction rather than by accident.

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
| Trailing 5+ | 0.43 | **0.61** | 0 |
| Trailing 9+ | 0.17 | **0.29** | 5 |

Most of the extra spread in the two-score version is sampling noise: a team's
gear change over the first half of the season barely predicts its own gear change
over the second half. Trailing 5+ is both more reliable and gives every team a
number.

For reference, neutral seconds per play itself splits at **r = 0.82**. That
column is solid.

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

**Seconds per play — not adjusted.** Defences vary in the pace they face by only
0.47s standard deviation, and averaged over a 17-game schedule that collapses to
**0.13s SD with a 0.61s total range across all 32 teams**. Against a team spread
of 5.7 seconds, adjustment reproduces the unadjusted column with a decimal
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
correlates with seconds per play at −0.17** — essentially nothing.

Cleveland runs the league's shortest drives (160s, 5.48 plays) while sitting
mid-pack in actual tempo at 40.4s per play. Buffalo has the longest drives (206s,
6.53 plays) and is one of the *slowest* teams at 41.9s per play.

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
TimeSinceSnap, Huddle, HomeRoad, GameClock, GameId, PlayId,
DriveStartClock, DriveEndClock, DriveResult
```

That split is deliberate. Rather than checking by hand which historical sheets
carry `TimeSinceSnap`, run the workflow with **Rebuild every season** ticked and
read the log: every season without it prints a warning and is left out of
`pace_index.json`, so the tool only offers seasons that will actually render.
