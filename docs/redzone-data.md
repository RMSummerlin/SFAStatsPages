# Red zone tools: data decisions

How the two red zone tools are built from the season sheets, why each
definition is what it is, and what will look like a bug but is not. One pull
(`scripts/pull_redzone.py`) feeds both pages:

| Page | Fragment | Season file | Shortcode |
|---|---|---|---|
| NFL Red Zone Targets and Carries (player usage) | `tools/redzone/` | `data/redzone_<season>.json` | `[sharp_football_redzone]` |
| NFL Red Zone Stats (team offense and defense) | `tools/redzone-team/` | `data/redzone_team_<season>.json` | `[sharp_football_redzone_team]` |

Figures quoted below come from the 2026 export through week 5.

## Source

The season Google Sheets in `scripts/config.py`, same as every other tool.
Nothing is read from nflverse: the sheet carries the target, rusher and
passer IDs (GSIS format), the target's position, the yard line, the drive
number and result, EPA, success and the running score, which is everything
both pages need. The matchup pull's cached `data/schedule_<season>.json` is
read if present, only to price the try on a touchdown drive that ended a game
(see points per trip); it is never fetched by this pull.

The sheet is read through `offense.offense_rows()` like every other pull, so
a mirrored export (each play logged once per team) folds to the offense's
rows. The 2026 sheet stopped being mirrored in October 2026; the fold stays
in case it comes back.

## Yard lines and bands

`los` is yards to the opponent's goal line. The red zone is 20 or closer.
Counts are stored in three bands so the tool's zone toggle needs one file:

| Band | Yard lines | Inside the 20 | Inside the 10 | Inside the 5 |
|---|---|---|---|---|
| 0 | 20 to 11 | yes | | |
| 1 | 10 to 6 | yes | yes | |
| 2 | 5 to 1 | yes | yes | yes |

The toggle sums the bands it covers. Every figure on the player page, the
share columns included, is read inside the zone showing.

## Player usage

| Term | Built from |
|---|---|
| Target | a `PlayType` PASS row with a `TargetID`. A sack or a throwaway has none and is nobody's target |
| Reception | `Cmp` on that row |
| Carry | a `PlayType` RUSH row with a `RusherID`. Scrambles (`Scramble?`) are carries for the quarterback, so a QB's row holds designed runs and scrambles together |
| Opportunity | target plus carry. The word is deliberate: not every target is caught, so "touches" would overstate it |
| Touchdown | `PlayResult` TD on the target's or the rusher's row |
| TD % | the player's touchdowns over his team's red zone touchdowns. A share, not a rate: touchdowns per opportunity is in the detail card only |
| Target share, carry share | the player's targets (carries) over his team's red zone targets (carries) over **every game the team played** in the weeks picked, not only the games he played, so a back who was on the field for two games does not read a 60% share of six carries. A player who changed teams is read against each team for the weeks he was on it, with the move placed at his first red zone week with the new team |
| Opportunity share | targets plus carries over the team's targets plus carries, on the same denominator. The one that matters for a back who does both; in the detail card, not the table |
| Games (G) | weeks with a target or a carry **anywhere on the field**, not just the red zone. Most players go a week without a red zone opportunity and still played |
| Opp/G | opportunities over games |
| Last 4 | opportunities inside the zone in the player's last four games (by the games definition above). A game without red zone work counts as zero, a game not played does not count |

Kneels and spikes are excluded everywhere (the shared `DEAD_BALL_RE`). A
kneel at the 1 is not a carry. Two-point tries are not in the sheet (the
`p2PtAtt` column is all zero and no row carries a down of 0), so they are not
in the counts.

### Positions

The sheet tags the position of the targeted player (`TargetPos`) and nothing
else, so rushers need inferring. In order:

1. A player who threw more passes than he had targets or carries is a QB.
2. Otherwise his most common target tag among QB, RB, WR, TE. A player
   tagged DB who is targeted is a two-way player lined up as a receiver and
   reads WR; a lineman who caught a tackle-eligible pass reads TE
   (`TAG_FOLD`).
3. A rusher who is never targeted is a RB.

`POSITION_OVERRIDES` in the pull takes a player ID to a position for anyone
the rules get wrong. It is empty. Of the 214 rushers through week 5, 191
were placed by rules 1 and 2 and the remaining 23 (never targeted) are all
backs.

### Plays nullified by penalty

Dropped, as official statistics do. In practice the provider's export does
not carry them: all 158 penalty rows in the 2026 sheet through week 5 are
plays that stood, either with the yardage to the spot of a foul beyond the
line (a holding call on a run that gained 8 is recorded as a 2-yard carry to
the spot of the hold, which is also the official statistic) or with the foul
tacked on after the play. The guard, `negated_by_penalty()`, drops a row
only when a play-cancelling foul (holding, pass interference, illegal
formation, illegal contact and the like, not grounding or a dead-ball foul)
was enforced from the previous spot on a row with no result and no yards,
which is what a nullified play would look like. It caught one row in 2026: a
Malik Willis pass with an illegal touch. Defensive holding and face mask
rows stay: the provider marks them FIRST DOWN with the play's own yards, and
the enforcement spot shows they were added on at the end of the run.

## Team efficiency

| Term | Built from |
|---|---|
| Trip | a drive with at least one pass or rush snap at 20 yards to goal or closer, **kneels excluded**. An offense that kneels out at the 15 is not charged a failed trip. This is the one place the figure differs from the box score tool, whose red zone trip count includes kneel-only drives: eight of the league's 517 drives through week 5 |
| Touchdown trip, field goal trip | `DriveResult` Touchdown, Field Goal |
| TD %, scoring % | touchdown trips over trips; touchdown plus field goal trips over trips |
| Points per trip | a touchdown is 6 plus whatever the try added, read from the team's score on the game's next snap (either team's row carries both scores), capped 0 to 2; the final score from the cached schedule prices a drive that ended the game, and 7 is assumed only if neither is available. A field goal is 3. Same pricing as the box score tool's points per drive |
| Plays per trip | red zone snaps (kneels out) over trips |
| EPA per play, success rate, pass rate | `EPA`, `SuccessPlay` and dropbacks (PASS plus scrambles) over red zone snaps |
| Turnovers | `PlayResult` INT, FUMBLE LOST or DEF TD on red zone snaps |
| Goal-to-go TD % | trips with a goal-to-go snap (`dist` at least `los`), converted on a touchdown |
| Inside-10 TD % | trips with a snap at 10 or closer, converted on a touchdown |
| Last 4 TD % | TD % over the team's last four games in range |
| Defense | the same figures for the offenses a defense faced. A defense's week is exactly the offense cell of its opponent, found through the opponent code the cell carries, so nothing is stored twice |

Rank badges are best first on the side in view: for the offense a high TD %
ranks 1, for the defense a low one does. Plays per trip and pass rate carry
no badge; neither has a better side. The NFL row pools every trip in view,
so it is the league rate rather than the mean of 32 team rates.

### Trips agree with the box score tool

Season totals per team through week 5 match the box score tool's `rz_trips`
and `rz_td` exactly, apart from the kneel-only drives above (seven teams, one
or two drives each, no touchdowns among them). Touchdown trips agree on all
32 teams.

## Season files

Both files recompute in the browser from weekly cells, so the week pick,
the zone toggle and the position filter never need a round trip.

`redzone_<season>.json`:

```
players: { "<gsis id>": { n: name, p: position, t: latest team,
                          g: [weeks with any opportunity on the field],
                          w: { "<week>": [team, band0, band1, band2] } } }
            band = [targets, receptions, receiving TDs, carries, rushing TDs]
tw:      { "<team>": { "<week>": [opponent, band0, band1, band2] } }
            band = [targets, carries, plays, dropbacks, TDs]
```

Only red zone weeks are stored under `w`; `g` is the whole-field games
list. 2026 through week 5 is 66 KB for 321 players.

`redzone_team_<season>.json`:

```
tw: { "<team>": { "<week>": [opponent, trips, TD trips, FG trips, points, plays,
                             dropbacks, EPA, successes, giveaways,
                             goal-to-go trips, goal-to-go TDs,
                             inside-10 trips, inside-10 TDs] } }
```

8 KB for a full season. `schema` is bumped in the pull whenever either shape
changes.

## Preload tables

`redzone_preload.html` is the top 50 players by opportunities inside the 20
with games, targets, receptions, carries, opportunities, touchdowns, TD
share and both shares, followed by the top 20 by carries inside the 5. Full team
names, so the long-tail "chargers red zone targets" searches land on real
words. `redzone_team_preload.html` is the 32-team offense table and the
32-team defense table, each ranked by TD %. All captions carry "through
Week N". The tools hide them once painted.

## Things that will look like bugs but are not

**A player's target share is 0% with targets on the table.** He has carries
only inside the zone showing; the share is of targets. The detail card's
opportunity share combines both.

**TD % is not touchdowns per opportunity.** It is the player's share of his
team's red zone touchdowns inside the zone showing. The per-opportunity rate
is in the detail card.

**A back who played two games shows a 15% carry share, not 60%.** Shares are
read against every game the team played in the weeks picked. Pick only his
weeks to read him against the games he played.

**Games (G) is 5 for a player with one red zone week.** G counts every game
with a target or a carry anywhere on the field.

**Last 4 is less than opportunities per game would suggest.** The last four
games include games without red zone work, which count as zero.

**The box score tool shows a team one or two trips higher.** Kneel-only
drives, above.

**Points per trip reads 7.00 on a one-trip week.** The try is read from the
next snap; a touchdown that ended a game with no cached schedule to price it
is assumed 7.

**A quarterback leads the carries board.** Scrambles are carries. That is
how the usage reads for a running quarterback and is on purpose.

**A player shows one team in the table and another in the detail title.** The
table shows the team he is on now; the shares and the chart read the team he
was on each week.

**The Teams view opens on a team nobody picked.** With no team in the link it
opens on the team with the most red zone plays in range. `#teams/kc` opens
on Kansas City.
