# Box Scores

One played game at a time: the scoreline, seven diverging bars showing which
team was better in each category and by how much, and an offensive box score
underneath in four groups (box score, efficiency, passing, rushing and
tendencies) with each team's season average alongside once it has more than
one game. Season select, week stepper and a game picker that doubles as the
slate view. Opens on the newest season's latest played week.

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
* The bottom sheet is `position:absolute` inside the root and scrolls
  internally. No `position:fixed`.
* At 641px and up the four tables sit two across; on a phone they stack.
* Stat rows, groups and header categories come from the data file, so adding
  a stat is a pull edit. The tool only knows how to format each `kind`.

## Things that look like bugs but are not

* **The stepper stops at the latest week with a game in the data**, not the
  current week, and past seasons open on week 18. There is nothing to show for an unplayed game. A partly
  played week (Thursday in, Sunday not) shows with the unplayed games greyed
  in the picker.
* **A game the sheet has but the schedule lacks, or where the two disagree on
  the opponent, does not appear.** The pull prints a NOTE naming it.
* **No season column in week 1.** See the docs.
* **The verdict says the loser was better in more categories.** That is the
  point of the header.
