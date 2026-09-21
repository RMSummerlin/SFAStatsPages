# NFL Matchups: talking points and surrounding copy

Source text for the article that wraps the tool at
`/stats-nfl/nfl-matchup-stats/`. Everything the tool used to explain inside
its own footer and "How to read this" panel now lives here, plus the season
blending plan, so the page copy can say as much or as little as it wants. Written
to be lifted, trimmed, or rewritten; nothing here is locked.

The tool itself shows only ranks, edges and the numbers behind them. Method
detail belongs on the page, not in the widget.

---

## Intro (above the tool)

Every NFL game is really two games: one offense against one defense, then the
reverse. The matchup tool shows both halves of every game on this week's slate,
one game at a time. Pick a game, and each side of the ball gets five rows:
overall efficiency, passing, rushing, pressure, and explosive plays. On each
row the offense's league rank sits on the left, the defense's on the right, and
the bar between them shows which unit holds the edge and by how much.

Ranks run 1 to 32 for the unit named, so a defense ranked 3rd is a top-three
defense. The bar grows from the middle toward whichever team has the advantage,
in that team's color. A bar that fills its whole half is a 1st-ranked unit
against a 32nd-ranked one. "Even" means the two units are within a few ranks of
each other.

Tap any row for the numbers behind the rank: the efficiency stats that make up
the rating, how each unit has trended week to week, and where a defense's
tendencies meet the offense's answer to them, such as how often the defense
blitzes against how the offense performs when blitzed.

Use the game menu to jump between games or sort the slate by biggest mismatch.

## How to read the five rows

**Overall.** A blend of success rate (60%) and EPA per play (40%) across every
pass and run. Success rate rewards staying on schedule; EPA rewards the plays
that swing the game. Success rate gets the larger weight because it is the more
stable of the two from week to week and year to year.

**Passing.** The same blend on dropbacks only, counting sacks and scrambles as
pass plays.

**Rushing.** The same blend on designed runs, with scrambles removed.

**Pressure.** How often a dropback ends with the quarterback pressured. For the
offense that is pressure allowed; for the defense, pressure generated. This is
the trench read, and it is one of the most stable things a unit does.

**Explosives.** The share of plays that go for 15 or more yards through the air
or 10 or more on the ground, for the offense, and the share allowed, for the
defense.

## What the ranks are built from

Every rating uses play-by-play data from every game this season, blended with
last season's numbers and adjusted for the opponents each unit has faced. The
blend is what keeps the ranks from lurching around on two weeks of data, and it
is what lets the tool show something useful in week 1.

### Why last season's numbers are pulled toward average

A team's rating from last season is not used as-is. It is pulled part of the way
back toward league average first, because a team's strengths and weaknesses
rarely carry over in full from one year to the next. Across the last five
seasons, roughly 40 to 50 percent of an offense's edge over average survived
into the following year, and only 20 to 30 percent of a defense's did.

Two things pull a team's baseline further toward average:

* **A new starting quarterback.** When the primary passer changes, last season's
  offensive numbers become far less useful: the year-to-year correlation of
  offensive efficiency falls by more than half. Those offenses start the season
  closer to the middle of the pack, whatever last year's ranking said.
* **A new head coach or coordinator.** A scheme change gets a smaller haircut
  than a quarterback change, on the offense for a new head coach or offensive
  coordinator, on the defense for a new head coach or defensive coordinator.

The practical effect in week 1: offenses that ran it back keep most of their
ranking, offenses with a new quarterback bunch toward the middle, and defensive
ranks are compressed across the board because defense is much less predictable
year to year than offense.

### How the blend changes as the season goes on

The tool never flips a switch from "last year" to "this year." This season's
games simply count for more each week, and last season fades on the same clock.
Roughly:

| Week | Share of an offense rating from this season | From last season's baseline |
|---|---|---|
| 1 | 0% | 100% |
| 2 | about 12% | about 88% |
| 4 | about 30% | about 70% |
| 6 | about 44% | about 56% |
| 8 | about 54% | about 46% |
| 10 | about 62% | about 38% |
| 14 | about 73% | about 27% |
| 18 | about 81% | about 19% |

Defense leans on the baseline a little longer than offense, because defensive
numbers are noisier and need more games before they mean much. Most of what the
"baseline" does after the first month is not remembering last season so much as
holding a rating near league average until this season's sample is large enough
to move it, which is the same reason a small-sample rank in any stat should be
read with caution.

Ranks for each week are frozen as of that week. The week 3 card always shows
what the ratings were going into week 3, even after the games are played.

### Opponent adjustment

The five headline rows are adjusted for the opponents each unit has faced, so an
offense that has played three top defenses is not penalized for a schedule it did
not choose. Splits in the tap-through detail (blitz, coverage, play action, deep
passing and so on) are not adjusted; their samples are too thin for that to be
meaningful early in the year.

### What this is and is not

The tool describes how each unit has performed and how the two line up. It is
not a projection or a pick. A big edge on one row is a reason to look closer,
not a reason to bet.

## Outro (below the tool)

Quick reads for bettors and fantasy managers from the matchup tool:

* **Passing edges matter most.** Passing efficiency is both the most stable
  unit-level stat and the one that most decides games, so a lopsided passing
  row is the strongest signal on the card.
* **Pressure is the one trench number that holds up.** A defense that generates
  pressure against an offense that allows it is the matchup that shows up in
  sacks, turnovers and stalled drives.
* **Be careful with rushing edges.** Rushing efficiency is the noisiest of the
  five rows from week to week; treat a big rushing edge as a note, not a lean.
* **Defensive ranks move slowly for a reason.** Early in the year defensive
  ranks sit closer to the middle than offensive ranks. That is the model being
  honest about how little three games of defensive data tell you, not a
  statement that the defenses are all the same.
* **Check the trend.** Tap a row and look at the rating-by-week line. A unit
  that has climbed steadily since week 1 is telling you something the season
  rank alone does not.

## FAQ blocks (optional, for the bottom of the page)

**What is EPA per play?** Expected points added: the change in expected points
from before a play to after it, given down, distance and field position. A
positive number means the play left the offense better off than average.

**What is success rate?** The share of plays that keep an offense on schedule:
gaining 45% of the distance to go on first down, 60% on second, or converting on
third and fourth. The threshold is rounded to whole yards, so first-and-10 needs
5 and second-and-7 needs 4. Full definition and where it comes from:
`docs/metric-definitions.md`.

**Why does a defense's rank bunch toward the middle early?** Defensive efficiency
is far less predictable from one season to the next than offensive efficiency,
so the model starts every defense closer to average and lets this season's games
spread them out.

**Why does a team with a new quarterback rank lower than last year?** Last
season's offensive numbers belonged to a different quarterback, so the baseline
is pulled harder toward league average until the new offense has its own sample.

**When does last season stop counting?** It never drops off in a single step. By
midseason it is a minority of the rating; by the last month it is a small share
that mostly keeps a rating near average when the current sample is thin.

**How often does it update?** Ratings refresh as soon as a new week's play-by-play
lands, and the week rolls over on Tuesday after Monday night.
