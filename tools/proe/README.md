# NFL Pass Rate Over Expected

Three tabs. **Offense** and **Defense** rank the 32 teams on pass rate over
expected (PROE) and on their last four games, with a season multi-select, a
week range, and quarter and down multi-selects. Every team row expands to its
week-by-week PROE across all 18 weeks, bye marked, unplayed weeks empty, one
chart per selected season. **Matchups** is one table for the week, a row for
every offense against the defense it faces, sortable on either side's PROE or
on their sum.

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
| `proe_<season>.json` | on demand, as seasons are selected; per team-week dropbacks, expected dropbacks and plays for the offense and for the defense it faced, the same offense sums split by quarter and down, plus the schedule, byes and the current week |

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

Every figure is centred so the league averages zero within each season: the
season's league over-expected rate on the plays in view is subtracted before
anything is summed or pooled. See `docs/proe-data.md`.

## Quarter and down

Both chips are multi-selects; empty means all, and picking every option reads
as All. They narrow the plays behind every figure on the Offense and Defense
tabs: the table, Last 4, the expanded cards and the week-by-week chart. The
league centring is recomputed on the narrowed plays, so the NFL Average row
still reads 0.0. With no quarter or down picked the tool reads the published
team-week sums exactly as before; with either picked it sums the split cells
(`twq` in the season file) for the offense, and the opponent's split cells for
the defense, so both sides narrow to the same plays. The chips only appear
once every selected season carries the split, which seasons published before
schema 2 do not.

## Matchups

One table for the week: a row for every offense against the defense it faces,
so a week with no byes has 32 rows. Columns are the offense and its PROE, the
defense and its PROE against, and **Matchup**, the sum: an offense at +4
against a defense whose opponents sit at +3 projects to about +7. The table
opens sorted on Matchup, highest first, and any of the three figure columns
sorts; shading and ranks work as on the team tables. The team cells' tooltip
carries the game, with the final score once played. Figures are always the
season to date, whichever week the stepper shows, and the quarter, down and
week filters do not apply here. The stepper stops at the current week, which
flips the day after Monday night, same as the matchup tool.

## Embedding

Paste the whole of `embed.html` into an Avada custom code block. It is a
fragment: one `<style>`, one `<div class="pt-root pt-pr">`, one `<script>`.
Every selector is scoped `.pt-root.pt-pr`.

Shortcode for the crawlable table: `[sharp_football_proe]` in a **Text Block**
above the code block. The tool hides it once it has painted.

Run `python scripts/lint_embed.py tools/proe/tool.html tools/proe/embed.html`
before pasting.

## Things that will look like bugs but are not

**The NFL Average row reads 0.0 on PROE.** Figures are centred so the league
averages zero within each season on the plays in view. Expected rates come
from a fixed pool of completed seasons, and the league drifts from year to
year, so without the centring a run-heavy season would read a point below
zero across the board. One consequence: a team's number can move by a tenth
or two when other teams play, because the league mean moved.

**Last 4 equals PROE for the first month.** A team with three games played has
three games in both columns.

**A past week on the Matchups tab shows today's numbers.** By design. Figures
are season to date and never frozen per week; only the schedule belongs to
the week shown.

**No Quarter or Down chip on the bar.** Every selected season has to carry the
split cells (schema 2 of the season file). The pull rebuilds every season the
first time it runs after the schema bump, so this clears itself on the next
scheduled run.

**Picking all four quarters and overtime, or all four downs, says All.** It is
the same set of plays, and the chip says so rather than counting.

**Several seasons selected, one row per team.** Seasons pool into one figure,
like the pace tool. The expansion shows one chart per season, newest first.

**A dash in Last 4 with a number in PROE.** The week range excludes every game
the team played in the newest season, but includes games from an older one.
