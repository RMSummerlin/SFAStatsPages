# NFL Red Zone Targets and Carries

Player usage inside the 20, 10 or 5. Three tabs. **Players** ranks every
player with red zone work on targets, receptions, carries, opportunities,
touchdowns, TD rate, target share, carry share, opportunities per game and
the last four games, with position pills, a season pick, a week multi-select, a
team filter and a minimum-opportunities filter; the first 50 show until
"show all" is tapped. Every row expands to cards, a zone split (20 / 10 / 5)
and a week-by-week chart of targets over carries with a dot per touchdown.
**Teams** is one offense at a time: a header line with its red zone plays,
pass rate and the share of plays that scored, then every player with shares
and the latest game beside the season. **Leaders** is three pre-sorted
boards: carries inside the 5, targets inside the 10, opportunities inside
the 20; tapping a name opens his row on the Players tab.

There is no explanatory copy inside the tool on purpose: definitions belong
in the article around it. Data decisions are in `docs/redzone-data.md`.

## Files

| File | Role |
|---|---|
| `tool.html` | Working copy with every note. Edit this one. |
| `embed.html` | Same fragment, comments stripped. Paste this one into Avada. Rebuild with `python scripts/build_embed.py`. |

## Data it fetches

Base URL `https://rmsummerlin.github.io/SFAStatsPages/data/`

| File | When |
|---|---|
| `redzone_index.json` | on load: which seasons exist, which is the default |
| `redzone_<season>.json` | on demand, as a season is picked; per player-week targets, receptions, carries and touchdowns in three yard-line bands, each team's weekly totals, and every player's position, current team and games played |

Both are written by `scripts/pull_redzone.py`, which also writes the team
page's files. Every figure is computed in the browser from the weekly
cells, which is what lets the zone toggle, the week pick and the position
filter recompute on the spot.

## What the columns mean

- **Tgt, Rec, Car**: targets, receptions and carries inside the zone showing.
  Scrambles are carries for the quarterback. Kneels are nothing.
- **Opp**: opportunities, targets plus carries. Not touches: not every
  target is caught.
- **TD, TD %**: touchdowns on those opportunities, and per opportunity.
- **Tgt %, Car %**: the player's share of his team's red zone targets
  (carries) in the games he played, on the team he was on that week. The
  combined opportunity share is in the expanded card.
- **G**: games with a target or a carry anywhere on the field.
- **Opp/G**: opportunities over G.
- **Last 4**: opportunities in the player's last four games among the weeks
  picked; a game without red zone work counts as zero.
- **Weeks**: a multi-select. Tap each week to include it, so the games a
  player missed can be left out one at a time; nothing picked means every
  week.
- **Rank**: standing on the sorted column, highest first. Sorting ascending
  counts down rather than renumbering.

## Deep links

Hash based, like the box score and matchup tools, so a cached page serves
every variant. Tokens combine with a slash in any order.

| Token | Means |
|---|---|
| `#zone10`, `#zone5` | the yard-line toggle (inside the 20 is the default) |
| `#qb` `#rb` `#wr` `#te` | the position pill |
| `#kc` | the team filter; on the Teams tab, the team shown |
| `#teams`, `#leaders` | the tab |
| `#w3-7`, `#w5`, `#w1-3,6,9` | the weeks picked: runs, single weeks, or both |
| `#min10` | the minimum-opportunities filter (1, 5, 10 or 20) |
| `#2025` | the season |
| `#derrick-henry` | opens that player's row |

So `#teams/lac` is the Chargers' red zone usage and `#zone5/rb` is the goal
line back table. The tool rewrites the hash as the reader changes things.

## Embedding

Paste the whole of `embed.html` into an Avada custom code block. It is a
fragment: one `<style>`, one `<div class="pt-root pt-rz">`, one `<script>`.
Every selector is scoped `.pt-root.pt-rz`.

Shortcode for the crawlable tables: `[sharp_football_redzone]` in a **Text
Block** above the code block (the top 50 by opportunities and the top 20 by
carries inside the 5). The tool hides it once it has painted.

`TEAM_PAGE` at the top of the script is the link the Teams tab's header line
points at for trips, TD rate and points per trip. Set it to the team page's
final URL, or empty it to drop the link.

Run `python scripts/lint_embed.py tools/redzone/tool.html tools/redzone/embed.html`
before pasting.

## Things that will look like bugs but are not

See the end of `docs/redzone-data.md`: target share at 0% for a back with
carries only, G counting whole-field games, Last 4 including games without
red zone work, quarterbacks on the carries board, and the Teams tab opening
on the busiest offense when the link names none.
