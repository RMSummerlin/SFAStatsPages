# Personnel Grouping Frequency — full grid

Option A of two. Recreates the old Tableau dashboard: every offense as a row, every
personnel grouping as a column, heat-shaded by frequency.

- **Fragment:** `tool.html` — paste the whole file into an Avada custom code block.
- **Data:** `data/personnel_grouping_<season>.json`, listed by
  `data/personnel_grouping_index.json`.
- **Root class:** `.pt-root.pt-pgf`. All CSS is scoped to it, so this tool and the
  compact one can sit on the same page without clashing during review.

## What it shows

Rows are offenses, columns are personnel groupings ordered by league-wide usage. Each
cell is that grouping's share of the offense's filtered plays with the snap count
beneath, shaded light to Sharp red against the highest cell in view. The right-hand
column is total plays with a league rank; the bottom row is the league.

Columns fold on RB-TE, so `12` is 1 RB and 2 TE regardless of receiver count — see
`docs/personnel-grouping-data.md`. Groupings past the top 12 collapse into an `Other`
column. Tapping an offense opens its exact personnel breakdown, including which snaps
were six-OL looks.

Any column header sorts. First click is A–Z for the offense column and highest-first for
everything numeric.

## Filters

Season, week, quarter, down and field zone are multi-select — nothing selected means no
filter on that field. Yards to go and score margin are dual-thumb ranges. Play type is
dropback or designed run. RB / TE / WR counts are multi-select and use exact counts.

**Neutral game script** sets quarters 1–3 and margin within 14 points. Touching quarter
or margin afterwards releases the checkbox, so the controls never lie about what is
applied.

## Mobile

~75% of traffic, so: the root is a bounded 85svh flex panel with its own scrollbar, the
offense column is frozen while groupings scroll horizontally, the header row and league
row stay pinned, and the filter panel collapses behind a Filters button showing a count
of what is active. Grouping headers are two digits precisely so several fit on a phone.
Desktop enhancement starts at `min-width: 641px`.

## Search engines

`tool.html` ships with a real 32-row HTML table between the `SFA:PRELOAD` markers,
holding unfiltered season totals. Crawlers get a complete table with no JavaScript; the
live tool replaces it on load. Refresh it with:

```
python scripts/pull_personnel_grouping.py
python scripts/refresh_preload.py
```

then re-paste `tool.html` into Avada. The interactive tool is always live regardless —
only this static snapshot goes stale.

## Before shipping a change

```
python scripts/lint_embed.py tools/personnel-grouping-full/tool.html
```
