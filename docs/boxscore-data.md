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

Every count and rate is built from **pass and rush plays**. So:

* Every number is the offense's. "Pressure rate" is pressure allowed;
  "blitz rate" is blitzes faced.
* Penalty-only plays do not exist in the data. The SNAP chart's penalty
  category was dropped rather than faked from another source, whose EPA
  would not agree with the sheet's.
* Kneels and spikes are excluded from every play count and rate, using the
  same word-bounded regex as the other pulls. Their drives still count as
  drives and their clock still counts toward possession.
* **Special teams rows** (`PlayType` `KICKOFF`, `PUNT`, `FGA`, `XPA`,
  `TWOPOINTCONV`) arrived with the 2026 week 6 export; the 2021–2025 sheets
  have none. They are read for exactly one thing — a kickoff or punt the
  receiving team fumbled or muffed to the kicking team is a turnover — and
  otherwise dropped, so plays, drives, EPA, success and possession are the
  same with or without them. The SNAP chart's special teams category is still
  not shown. A season's `excluded` object counts them under `special teams`,
  and the run log says how many turnovers were read from them.

## Definitions

| Stat | Built from |
|---|---|
| Plays, yards, yards per play | pass and rush rows; `Yds` on a sack is negative, so passing yards are net |
| First downs | `PlayResult` FIRST DOWN or TD. Penalty first downs already carry FIRST DOWN on the play they came with |
| Third and fourth down | attempts on that down, converted on FIRST DOWN or TD |
| Turnovers | `PlayResult` INT, FUMBLE LOST or DEF TD (a pick-six or fumble return is DEF TD) on pass and rush plays. A fumble the offense recovered is FUMBLE and is not one. Plus, where the sheet has kickoff and punt rows, a return the receiving team fumbled or muffed and the kicking team recovered — see below |
| Turnover EPA | sum of EPA on those plays; negative is what the offense gave away. A kickoff or punt row's EPA is from the kicking team's point of view, so it enters with its sign flipped |
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

### Special teams turnovers

Kickoff and punt rows carry no `PlayResult`, so the turnover is read from the
gamebook text in `PlayDesc`, by `kick_turnover()` in the pull:

* The play has a `FUMBLES` or `MUFFS`, and the last `recovered by XXX-` on
  it names the kicking team. A punt row is on the punting team's drive, so
  the kicker is the row's `team` and the turnover is charged to its
  `opponent`; a kickoff row is on the receiving team's drive, so the kicker
  is read from `kicks N yards from XXX 35` (falling back to the row's
  opponent) and the turnover is charged to the row's `team`.
* Replay can erase one. The gamebook then restates the play after the word
  `REVERSED`, and only the text after the last reversal is read. Three
  kickoff fumbles in weeks 1–6 of 2026 were overturned this way; the drive
  chart (`DriveResult`, `DrivePlays`) agrees they were not turnovers.
* A loose ball the receiving team got back, or that went out of bounds, is
  not a turnover. Neither is a blocked punt or field goal the defense
  recovers, even one returned for a score (the provider marks it DEF TD),
  nor an onside kick the kicking team recovers: as in the official box
  score, a turnover is an interception or a fumble lost. Fake punts and
  field goals arrive as pass or rush rows and are handled as any other play.
* The provider's `HST`, `BLT`, `ARZ`, `CLV` and `LA` fold through
  `config.canonical_team` before comparing.

On the week 6 export this read 16 turnovers from 2,459 special teams rows: 9
kickoff fumbles and 7 muffed punts, each cross-checked against the drive
chart: the kickoff drives end in `Fumble` with zero plays, and the punting
team owns the drive after each muffed punt. They publish as `st_to` beside `to`, and also add to
`fum_lost`. `st_to` is 0 for a team with none once the sheet has any kickoff
or punt row, and absent (a dash, if it is ever shown) for the 2021–2025
seasons, whose turnover counts are the offense's alone.

A counter whose source column is in the sheet publishes as 0 when nothing
incremented it: no turnovers is a number. A counter whose column is absent
(older sheets lack `TTT`, the drive clocks and so on) is left out, and the
tool shows a dash.

## Quarters

The box score tables can show one quarter (or overtime) instead of the whole
game. The scoreline, the verdict and the header bars stay full game: the
control sits between the bars and the tables because that is all it changes.

* Every play adds to a per-quarter counter for its team-game through the same
  statements that build the game line (`Tally` in the pull), so a quarter's
  box score is exactly the game's arithmetic applied to that quarter's plays.
  The quarter counters sum to the game line.
* **A drive is credited to the quarter it started in.** Drives, points per
  drive, average start, red zone trips and time of possession all follow the
  drive, so a drive that crosses the quarter break sits wholly in the earlier
  quarter and a second-quarter possession clock can exceed 15:00. The tool
  does not say this; this document does.
* A kickoff or punt turnover lands in the quarter of its row.
* Every overtime period folds onto quarter 5, shown as OT. A game with no
  overtime play by either team shows "No overtime in this game" instead of
  tables.
* The season column becomes the team's per-game average for that quarter:
  the quarter totals carry the team's games played, so a team that never
  reached overtime has no OT average.
* The counters live in `boxscore_q_<season>.json`, which the tool fetches the
  first time a reader picks a quarter and keeps for that season. They are
  sparse: a counter the quarter never incremented is left out, and the tool
  reads a missing key as 0 wherever the game line carries the key, so a quarter
  without a sack reads 0% rather than a dash while a column the sheet lacks
  stays a dash in every quarter. Five copies of every game line would have
  tripled the season file, which every reader downloads; the quarter file is
  about the same size again but only a reader who picks a quarter pays for it.
* `quarters` in the season file says whether the sheet carried a `qtr`
  column. Without it the tool shows no control and no quarter file is written.

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

## Previous meetings

Each season file carries `meetings`: game id → the same two teams' three most
recent earlier games, newest first, as `[season, week, away, home, away pts,
home pts]`. The tool shows them as buttons under the date line, and each
opens that game's box score, loading its season if need be.

* Only games the box score data publishes count, so every button opens a box
  score. That means regular season, 2021 on: the Super Bowl and other
  playoff games are not in the sheets.
* A season's own earlier weeks count, so a division rematch lists the first
  game.
* The list only looks backward, so adding a season never changes an older
  file. The pull reads the older seasons from their files on disk; an `--all`
  run goes oldest first and writes each before building the next.

## Things that look like bugs but are not

* **The season column is missing in week 1.** It appears once a team has two
  games; before that it would only repeat the game figure.
* **A team with no fourth-down attempt shows a dash, not 0/0.** A rate with
  no denominator has no value.
* **Points per drive does not match the final score divided by drives.**
  Defensive and special teams scores are not on any drive.
* **A team's turnovers can exceed its interceptions plus lost fumbles on
  offense.** From 2026 a fumbled kickoff or muffed punt counts, as it does in
  the official box score. The 2021–2025 seasons cannot count them, so a
  season-over-season comparison of turnovers is slightly uneven.
* **A kickoff the receiving team fumbled away is not a drive.** The drive
  count still needs a pass or rush snap, so such a possession adds a
  turnover but no drive, no start position and no clock — the same as the
  official drive chart, which gives it zero plays.
* **Time of possession in an overtime game sums to more than 60:00.** Correct.
* **The Rams appear as LAR.** `config.canonical_team` folds the sheet's `LA`
  and nflverse's `LA` onto it, and the Cardinals' `AZ` onto `ARI`.
