# Metric definitions

The wording to use when a tool, a page or an FAQ block explains a metric. One
file so the four tools cannot drift into four different definitions of the same
number.

Where a definition is the sheet's rather than ours, it says so and says how it
was checked. We publish these on the site, so a definition we cannot demonstrate
is a definition we should not print.

## Success rate

**The share of plays that keep an offense on schedule.** A play is a success
when it gains the yards the down asks for:

| Down | Needs |
|---|---|
| First | 45% of the distance to go |
| Second | 60% of the distance to go |
| Third and fourth | all of it — the conversion |

The threshold is rounded to whole yards and is never less than one, so
first-and-10 needs 5, second-and-7 needs 4, and third-and-2 needs 2.

For a defense it is the same flag read from the other side: every play that is
not a success for the offense is one for its defense. The tools show it as
success rate **allowed**, so a low number is a good defense.

Three things worth knowing before anyone asks:

- **Goal to go needs no special case.** Distance is already the yards to the
  goal line, so first-and-goal from the 3 needs 1 yard, like any first-and-3.
- **A turnover does not make a play unsuccessful.** The flag reads yardage
  against the threshold and nothing else, so a fumble after a 6-yard gain on
  first-and-10 is still a success. In the 2025 season 50 of 199 interceptions
  and lost fumbles are flagged successes.
- **It is not EPA.** Success rate counts plays that cleared a bar; EPA weighs
  how much each play was worth. That is why the matchup tool blends them rather
  than picking one.

### Where the definition comes from

Success is the one headline metric the pulls do not compute. `SuccessPlay`
arrives from the sheet as a 0/1 flag and every tool sums it as-is, so the
thresholds above are the sheet's, not ours. They were read off the 2025 export
by `scripts/derive_success_rule.py`, which anyone can re-run when a season
lands:

```
python scripts/derive_success_rule.py path/to/season_export.csv
```

On the 2025 export (33,327 plays) it reports:

- **45 / 60 / 100, rounded, minimum one yard, reproduces 33,325 of 33,327
  plays.** The two it misses are a pick-six and a fumble returned for a
  touchdown, both of which the sheet marks `PlayResult = TD` and flags a
  success although the offense gained nothing and the touchdown was the
  defense's.
- **The only first-down percentages that misclassify nothing are 45.00% to
  45.75%.** So the 40% figure this site used to publish was not a rounding
  choice, it was wrong: it disagrees with the sheet on 1,067 plays, 1,065 of
  them first downs that gained 33–40% of the distance and were flagged
  failures. The single commonest is first-and-10 for 4 yards, 1,011 plays on
  its own. Second down fits 59.50–60.50%, third and fourth 97–102%.
- **The sheet's own arithmetic agrees.** `AirYdsToSuccess` is the air yards a
  throw needed to succeed, so `AirYds - AirYdsToSuccess` is the yardage
  threshold stated by the sheet without reference to the flag. It matches the
  rule at 54 of 57 down-and-distance pairs, the three exceptions being rare
  distances where the most common value is drawn from a handful of throws.

The thresholds are whole yards, not a ratio, which is why second-and-4 for 2
yards is a success at half the distance: 60% of 4 rounds to 2. A definition
phrased as "gains at least 60% of the required yards" quietly gets those plays
wrong.

## EPA per play

Expected points added: the change in expected points from before a play to
after it, given down, distance and field position. A positive number means the
play left the offense better off than average. Comes from the sheet's `EPA`
column, offense's perspective throughout, so positive is always good for the
offense and a defense is judged on EPA allowed.

## Explosive plays

A pass gaining 15 or more yards, or a run gaining 10 or more. Set in
`pull_matchup.py` and shared by every tool, so the box score and the matchup
page always count the same plays.
