# Box Scores: data decisions

What the tool measures and where each number comes from. Read this before
changing `scripts/pull_boxscore.py`.

## What it shows

One played game at a time, away team on the left and home team on the right
throughout. Three parts:

1. **Scoreline** from the nflverse schedule, with each team's primary passer
   from the sheet.
2. **Header bars**: seven categories drawn as diverging bars. The fill grows
   from the centre toward the team that was better, in that team's colour, and
   its length is the actual difference over a fixed scale per category. Both
   teams' values sit at the ends. A one-line verdict counts the categories,
   which is where "the loser was better in 5 of 7" comes from.
3. **Box score tables** in four groups. Each cell is the game figure and, once
   a team has played more than one game, its per-game season average
   underneath. The better figure is bold where a stat has a better side.

The format is modelled on the SNAP-style "winner vs loser" chart, laid out
horizontally because seven columns do not fit a phone and seven rows do, and
kept as away vs home rather than winner vs loser so it reads the same way as
the matchup tool.

## What is in the data and what is not

The sheet carries **pass and rush plays only**. So:

* Every number is the offense's. "Pressure rate" is pressure allowed;
  "blitz rate" is blitzes faced.
* Special teams and penalty-only plays do not exist in the data. The SNAP
  chart's special teams and penalty categories were dropped rather than faked
  from another source, whose EPA would not agree with the sheet's.
* Kneels and spikes are excluded from every play count and rate, using the
  same word-bounded regex as the other pulls. Their drives still count as
  drives and their clock still counts toward possession.

## Definitions

| Stat | Built from |
|---|---|
| Plays, yards, yards per play | pass and rush rows; `Yds` on a sack is negative, so passing yards are net |
| First downs | `PlayResult` FIRST DOWN or TD. Penalty first downs already carry FIRST DOWN on the play they came with |
| Third and fourth down | attempts on that down, converted on FIRST DOWN or TD |
| Turnovers | `PlayResult` INT, FUMBLE LOST or DEF TD (a pick-six or fumble return is DEF TD). A fumble the offense recovered is FUMBLE and is not one |
| Turnover EPA | sum of EPA on those plays; negative is what the offense gave away |
| Drives | distinct `DriveNumber` per team-game, kneel drives included |
| Points per drive | a touchdown drive is 6 plus what the try added, read from the team's score at the start of its next drive (final score for the last drive) and capped at 2; a field goal drive is 3. So a missed extra point is 6 and a two-point conversion is 8 |
| Average start | mean `DriveStartDist` (yards to goal), shown as a yard line |
| Red zone TDs | drives with a snap at 20 yards to goal or closer, converted if the drive result is Touchdown |
| Time of possession | `DriveStartClock` to `DriveEndClock` per drive, crossing the quarter boundary as `pull_pace.py` does. The two teams sum to 60:00 on every non-overtime week 1 game |
| EPA, success rate | `EPA` and `SuccessPlay`, overall, on dropbacks (PASS plus scrambles) and on designed runs |
| Explosive plays | pass of 15+ yards or rush of 10+, the matchup tool's thresholds |
| Early-down success | downs 1 and 2 |
| Completions | `Cmp` over `Att` |
| Net yards per dropback | net passing yards over PASS rows (attempts plus sacks) |
| Depth of target, deep rate | `AirYds` over attempts; deep is 20+ air yards |
| Pressure, sack, blitz, play action | `PFFPrsrAlwd`, `PlayResult` SACK or `Sacked`, `Blitz?`, `PlayAct`, each over dropbacks |
| Time to throw | `TTT`, 0 to 15 seconds, over the dropbacks that carry one |
| Man coverage faced | `PFFCoverageType` 0, 1, 2M over man plus zone (2, 3, 4, 6) |
| Yards before and after contact | `YdsPreCt`, `YdsPostCt` over designed runs that carry them |
| 11 and 12 personnel | `OffPers` over plays with a grouping |
| Shotgun, no-huddle | `Shotgun`, `Huddle` over plays |

Every stat is published as a numerator and a denominator (or a plain count)
and the tool does the division, so the game line, the season column and the
league total all come from the same counters.

A counter whose source column is in the sheet publishes as 0 when nothing
incremented it: no turnovers is a number. A counter whose column is absent
(older sheets lack `TTT`, the drive clocks and so on) is left out, and the
tool shows a dash.

## Header bar scales

The difference that fills the whole half-track, set at the 99th percentile of
the absolute home-minus-away difference over 1,375 regular-season games (2021
to 2025 in full, plus 2026 week 1). A typical game fills about a third of the
track, a 95th-percentile blowout about three quarters, and one game in a
hundred reaches the end.

| Category | Scale | SD of the difference | 95th pct | 99th pct | Largest |
|---|---|---|---|---|---|
| Success rate | 30 pts | 11.0 | 21.9 | 29.9 | 46.8 |
| EPA per play | 0.70 | 0.26 | 0.53 | 0.68 | 0.89 |
| Dropback EPA | 1.10 | 0.40 | 0.79 | 1.12 | 1.82 |
| Rush EPA | 0.85 | 0.31 | 0.63 | 0.87 | 1.14 |
| Explosive plays | 10 | 4.1 | 8 | 10 | 16 |
| Pressure rate | 36 pts | 13.8 | 27.8 | 36.1 | 46.6 |
| Turnover EPA | 22 | 7.9 | 15.8 | 21.8 | 28.2 |

They are published in the data file, so changing one is a pull edit, not a
tool edit.

## Backfill check

Running the pull over the 2021 to 2025 exports (all columns present, 272
games a season, 271 in 2022 for the cancelled Bills-Bengals game) found:

* The two teams' possession sums to 60:00 within 30 seconds in every
  non-overtime game, and to more in every overtime game.
* Drive points never exceed the team's final score; the gap averages about
  one point a team-game, which is the defensive and special teams scoring
  that sits on no drive.
* Drives per team-game average 10.5 to 11.1, range 6 to 19.
* Every game in every sheet matched a schedule entry with the teams agreeing
  on each other as opponents.

## Inputs beyond the sheet

**Schedule:** nflverse `games.csv` through `pull_matchup.fetch_schedule`, so
the two tools share `data/schedule_<season>.json`. It provides home and away,
the final score, kickoff and the stadium. A game is published only when the
sheet has both teams' rows for that week, each names the other as opponent,
and the schedule lists the game; anything else prints a NOTE in the run log
and is left out rather than guessed.

**Which team is the offense:** the 2026 sheet may log every play twice. The
rows pass through `offense.offense_rows()` first, like every other pull.

## Things that look like bugs but are not

* **The season column is missing in week 1.** It appears once a team has two
  games; before that it would only repeat the game figure.
* **A team with no fourth-down attempt shows a dash, not 0/0.** A rate with
  no denominator has no value.
* **Points per drive does not match the final score divided by drives.**
  Defensive and special teams scores are not on any drive.
* **Time of possession in an overtime game sums to more than 60:00.** Correct.
* **The Rams appear as LAR.** `config.canonical_team` folds the sheet's `LA`
  and nflverse's `LA` onto it, and the Cardinals' `AZ` onto `ARI`.
