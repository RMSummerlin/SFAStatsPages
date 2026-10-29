# Box Scores

One played game at a time: the scoreline, seven diverging bars showing which
team was better in each category and by how much, and an offensive box score
underneath in four groups (box score, efficiency, passing, rushing and
tendencies) with each team's season average alongside once it has more than
one game. A segmented control between the bars and the tables shows one
quarter, or overtime, instead of the whole game; it changes only the tables,
and the season column becomes the per-game average for that quarter. Under the date line, up to three previous meetings of the same two
teams (2021 on), each opening that game. Season select, week stepper and a
game picker that doubles as the slate view: each game with its category count
large and seven small swatches for who took which category. Opens on the newest season's latest played week.

Data decisions and every stat's definition are in `docs/boxscore-data.md`.

## Files

| File | Role |
|---|---|
| `tool.html` | Working copy with every note. Edit this one. |
| `embed.html` | Same fragment, comments stripped. Paste this one into Avada. Rebuild with `python scripts/build_embed.py`. |

## Data it fetches

Base URL `https://rmsummerlin.github.io/SFAStatsPages/data/`

| File | When |
|---|---|
| `boxscore_index.json` | on load: which seasons exist, which is default |
| `boxscore_<season>.json` | on load for the default season, then on demand as a season is picked; cached after the first fetch. Schedule, every played game's counters, season totals, stat and header definitions |
| `boxscore_q_<season>.json` | the first time a quarter is picked for a season; cached after that. The same counters per quarter (1 to 4, 5 for overtime) for every game and every team's season, sparse |

Both written by `scripts/pull_boxscore.py`, which also needs the nflverse
schedule (shared with the matchup tool).

## Embed notes

* Root is `.pt-root.pt-bx`; every selector is scoped to the pair.
* Shortcode for the crawlable table: `[sharp_football_boxscore]` in a **Text
  Block** above the code block. `[sharp_football_boxscore game="CLE-JAX"]`
  (away team first) keeps just that game's two rows for a recap article.
* Deep links: `#w1-cle-jax` opens week 1, CLE at JAX, in the default season;
  `#2024-w18-cle-bal` opens another season. The tool rewrites the hash as the
  reader navigates, with `replaceState`, so it never adds history entries, and
  leaves the season off the hash while the default season is showing so links
  written before the season select keep working. A hash for a game that is
  not in the data, or a season the index does not list, falls back to the
  default season's latest week.
* The season select is a native `<select>`, single choice: box scores are one
  game at a time, so there is nothing to pool across seasons the way the pace
  tool does.
* The bottom sheet and its scrim are `position:fixed`, anchored to the viewport
  and capped at `84svh`; the sheet's list scrolls internally. This is the one
  modal the embed rules allow `position:fixed` for. The root itself has no
  height cap, so the page scrolls the tool.
* At 641px and up the four tables sit two across; on a phone they stack.
* The box score cells pin their borders with `!important`: on the live site's
  phone layout a theme rule drew a heavy box round every cell of the right
  figure column, and a class-scoped reset loses to an id-scoped or
  `!important` theme rule.
* Team colours come in three values, fill / text / fallback, shared with the
  matchup tool and explained in `docs/avada-embed-rules.md`. The real brand
  colour only paints the rule over the team name, the bars and the picker
  swatches; every letter and figure uses the darkened text value, so a
  Jaguars figure is no longer 3.1:1 teal. When two teams clash on either
  value, the home team falls back first.
* The header bars carry no caption and no quartile ticks. The better side's
  figure is bold in the team's text colour and the other side is muted grey;
  the gap is spoken in the row's `aria-label` and shown in the picker
  swatch tooltips.
* Stat rows, groups and header categories come from the data file, so adding
  a stat is a pull edit. The tool only knows how to format each `kind`.
* The quarter control appears only when the season file says `quarters` is
  true. The pick is kept across games and seasons, so stepping through a
  week shows the same quarter of each game, and it is not in the hash. If
  the quarter file fails to fetch the tables say so and the Game cell still
  works.

## Things that look like bugs but are not

* **The stepper stops at the latest week with a game in the data**, not the
  current week, and past seasons open on week 18. There is nothing to show for an unplayed game. A partly
  played week (Thursday in, Sunday not) shows with the unplayed games greyed
  in the picker.
* **A game the sheet has but the schedule lacks, or where the two disagree on
  the opponent, does not appear.** The pull prints a NOTE naming it.
* **No season column in week 1.** See the docs.
* **A quarter's drives, possession time or points per drive look too big.**
  A drive is credited to the quarter it started in, whole. See the docs.
* **The verdict says the loser was better in more categories.** That is the
  point of the header.
