# NFL Pass Rate Over Expected

Three tabs. **Offense** and **Defense** rank the 32 teams on pass rate over
expected (PROE) and on their last four games, with a season multi-select and
a week range. Every team row expands to its week-by-week PROE across all 18
weeks, bye marked, unplayed weeks empty, one chart per selected season.
**Matchups** lists the week's games with each offense's PROE beside the
defense it faces and the sum drawn as a lean on a centred track.

There is no explanatory copy inside the tool on purpose: definitions belong in
the article around it. Data decisions, the bucket definitions and the
validation against nflfastR are in `docs/proe-data.md`; the shared wording for
the metric is in `docs/metric-definitions.md`.

## Files

| File | Role |
|---|---|
| `tool.html` | Working copy with every note. Edit this one. |
| `embed.html` | Same fragment, comments stripped. Paste this one into Avada. Rebuild with `python scripts/build_embed.py`. |

## Data it fetches

Base URL `https://rmsummerlin.github.io/SFAStatsPages/data/`

| File | When |
|---|---|
| `proe_index.json` | on load: which seasons exist, which is the default |
| `proe_<season>.json` | on demand, as seasons are selected; per team-week dropbacks, expected dropbacks and plays for the offense and for the defense it faced, plus the schedule, byes and the current week |

Both are written by `scripts/pull_proe.py`. Every figure in the tool is
computed in the browser from the team-week sums, which is what lets the week
range and the pooled seasons recompute everything on the spot.

## What the columns mean

- **PROE**: dropbacks minus expected dropbacks, over plays, times 100, across
  the selected seasons and weeks. Positive means more pass calls than the
  situations warranted.
- **Last 4**: the same figure over the team's last four played games in the
  newest selected season, inside the week range. Early in a season it reads
  what there is.
- **Rank**: the team's standing on the sorted column, highest first. Sorting
  ascending counts 32 down to 1 rather than renumbering the rows.
- **Defense** tab: the same numbers for the offenses a defense faced. A
  positive figure means opponents pass more than expected against it.

Shading is diverging and value-based: teal for positive, red for negative,
depth against the largest figure in view. It carries *direction*, not quality.

## Matchups

Each game card has two rows, one per offense. The track is centred on zero and
fills toward the pass side (teal, right) or the run side (red, left) by the sum
of the offense's PROE and the defense's PROE against, against a full-track
value of 15 points. Figures are always the season to date, whichever week the
stepper shows. The stepper stops at the current week, which flips the day
after Monday night, same as the matchup tool. Played games show the final
score.

## Embedding

Paste the whole of `embed.html` into an Avada custom code block. It is a
fragment: one `<style>`, one `<div class="pt-root pt-pr">`, one `<script>`.
Every selector is scoped `.pt-root.pt-pr`.

Shortcode for the crawlable table: `[sharp_football_proe]` in a **Text Block**
above the code block. The tool hides it once it has painted.

Run `python scripts/lint_embed.py tools/proe/tool.html tools/proe/embed.html`
before pasting.

## Things that will look like bugs but are not

**The league average is below zero.** Expected rates come from the completed
seasons in `scripts/config.py`, and the league has leaned further toward the
run than that pool, so an average 2026 offense reads about a point negative.
The public nflfastR tables show the same effect, more strongly, because their
baseline is older.

**Last 4 equals PROE for the first month.** A team with three games played has
three games in both columns.

**A past week on the Matchups tab shows today's numbers.** By design. Figures
are season to date and never frozen per week; only the schedule and the
scores belong to the week shown.

**Several seasons selected, one row per team.** Seasons pool into one figure,
like the pace tool. The expansion shows one chart per season, newest first.

**A dash in Last 4 with a number in PROE.** The week range excludes every game
the team played in the newest season, but includes games from an older one.
