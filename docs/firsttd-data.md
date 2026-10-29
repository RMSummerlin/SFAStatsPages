# First touchdown tables: data decisions

What the two tables count and where each number comes from. Read this before
changing `scripts/pull_firsttd.py`.

## What they are

Two crawlable tables for the first and anytime touchdown article, with no
interactive tool over them. They reach the article through two shortcodes in
`wordpress/sfa-preloads.php`, each in its own Text Block, which is how one
article carries two tables when the page builder allows one code block.

1. **Team table** (`[sharp_football_firsttd_team]`): every team, with games
   played, how many times it scored the game's first touchdown, that rate,
   total touchdowns and offensive touchdowns. Ranked by first touchdown rate,
   then by first touchdowns, then total touchdowns.
2. **Player table** (`[sharp_football_firsttd_player]`): every player who has
   scored the first touchdown of a game, with how many times he did, how many
   times he scored his team's first touchdown (which includes the game's),
   and his touchdowns in all. Ranked by first touchdowns in a game, then team
   firsts, then total.

Current season only. The pull reads `config.CURRENT_SEASON`, so the tables
roll over to 2027 when that season's sheet is added. Older seasons can be
built offline with `--csv` and `--season`, which writes the season's JSON but
leaves the two tables as the newest season's.

## What counts as a touchdown

Every touchdown, however scored, because that is what the first touchdown
scorer market pays on.

| Kind | Read from |
|---|---|
| Offensive | a `PASS` or `RUSH` row with `PlayResult` TD, credited to the row's team |
| Defensive | a `PASS` or `RUSH` row with `PlayResult` DEF TD (a pick-six or fumble return), credited to the row's opponent |
| Special teams | a `KICKOFF`, `PUNT` or `FGA` row whose gamebook text says TOUCHDOWN. These rows carry no `PlayResult`. Credited to the last team named in a `RECOVERED by XXX-` on the play, if any (a muffed punt the kicking team fell on and ran in, a blocked kick the defense returned); otherwise a kickoff is returned by the row's team, which owns the receiving drive, and a punt or field goal by its opponent |

Not touchdowns:

* A touchdown the gamebook took back on the same play: the text after the
  last `REVERSED` is the only text read, and a `TOUCHDOWN NULLIFIED` or a `No
  Play` in it means no score. Pass and rush rows carry the provider's
  `PlayResult`, which already reflects this.
* A defensive return of an extra point or two-point try (`XPA`,
  `TWOPOINTCONV` rows). That is two points.

Special teams rows exist in the 2026 sheet from the week 6 export on, as a
full-season export, so every week's returns are in. The 2021–2025 sheets have
none, so an offline build of an older season counts only offensive and
defensive touchdowns.

## Order within a game

Touchdowns are ordered by `qtr` and then by `GameClock` counting down, with
`PlayId` as the tie-break and the row's position last. The first is the first
in time. Without a quarter and clock column the order is `PlayId` alone.

## Who scored

* An offensive touchdown's scorer is the sheet's `TargetName` on a pass or
  `RusherName` on a rush, the full name. A scramble with no rusher name falls
  back to `PasserName`. A pass or rush touchdown whose text has a `FUMBLE`
  (a teammate fell on it in the end zone) is read from the text instead, as a
  defensive one is.
* A defensive or special teams scorer only exists in the gamebook text, as
  `7-O.Oladejo`: the last player named before the word TOUCHDOWN in the text
  that stood. The jersey number is required, so a team code is never read as
  a name, and a second capitalised word is taken only for names like
  `A.St. Brown`.
* An abbreviated name is matched against the full names the sheet carries
  for that team (every passer, rusher and target). Exactly one name with that
  initial and surname gives the full name; otherwise the abbreviated form is
  kept. Defensive scorers have no offensive snaps, so they stay abbreviated
  in the player table, and the team table is unaffected either way. A
  touchdown with no name read at all is listed as Unknown and noted in the
  run log.
* A player is keyed by team and name, so a player traded mid-season appears
  once per team.

## Games played

The team table's denominator is games the team has a pass or rush snap in.
A game in which nobody scored a touchdown counts against both teams, so the
32 rates do not sum to one game per game.

## Things that look like bugs but are not

* **A team's first touchdowns plus its opponents' do not equal its games.**
  Games with no touchdown at all have no first.
* **A player's team firsts exceed his game firsts.** By design: a team's
  first touchdown includes the games in which it was also the game's first.
* **A returner's defensive score shows an abbreviated name while his catches
  show a full one.** The abbreviated name resolved to no single roster name.
  Check whether two players on the team share the initial and surname.
* **Overtime touchdowns order after the fourth quarter.** `qtr` 5 and up.

## Files

| File | Role |
|---|---|
| `data/firsttd_<season>.json` | every touchdown game by game (team, scorer, kind, quarter, clock), the team and player summaries, games played |
| `data/firsttd_index.json` | seasons on disk, for the status page |
| `data/firsttd_team_preload.html`, `data/firsttd_player_preload.html` | the two tables, folded into `data/preloads.json` by `preloads.py` |
