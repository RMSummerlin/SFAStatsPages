# Personnel Grouping Frequency — compact

Option B of two. Three columns instead of fifteen, with a per-team slide-out for the
detail.

- **Fragment:** `tool.html` — paste the whole file into an Avada custom code block.
- **Data:** `data/personnel_grouping_<season>.json`, listed by
  `data/personnel_grouping_index.json`.
- **Root class:** `.pt-root.pt-pgc`. All CSS is scoped to it, so this tool and the full
  grid can sit on the same page without clashing during review.

## What it shows

One row per offense with three numbers: **2+ RB**, **2+ TE**, **3+ WR**. Each cell has a
bar and a hairline tick at the league average, so above or below average reads at a
glance without a legend.

The three columns overlap on purpose. A 2-RB, 2-TE snap counts in both 2+ RB and 2+ TE; a
2-RB, 1-TE, 2-WR snap counts in 2+ RB only. They are three independent questions, not
shares of a whole, so they do not sum to 100%.

**Expanded** in the header swaps the three columns for the full grouping matrix — the
same data as the full-grid tool, without the heat shading.

## Team detail

Tapping an offense opens a panel beneath the row with three views:

1. **Personnel mix** — a donut of *Heavy* (2+ RB or 2+ TE), *3+ WR* with no extra back or
   tight end, and *Other*. A pie has to sum to 100%, so these three are mutually
   exclusive, unlike the table columns. That is why there is a third slice: without it,
   1-RB/1-TE/2-WR snaps would have nowhere to go.
2. **Week by week** — 2+ RB, 2+ TE and 3+ WR as lines, for spotting a mid-season shift.
   This chart applies every filter *except* week, otherwise selecting one week would
   collapse it to a single point. Weeks with fewer than 5 matching plays are skipped so
   thin samples do not read as real swings.
3. **Grouping breakdown** — the offense's top groupings as bars, each with a league
   average tick and the gap to league.

Across multiple seasons the trend chart runs weeks end to end with season labels beneath.

## Filters

Identical to the full-grid tool: season, week, quarter, down and field zone multi-select;
yards to go and score margin as dual ranges; dropback or designed run; RB / TE / WR
counts by exact number. **Neutral game script** sets quarters 1–3 and margin within 14
points, and releases if you touch quarter or margin afterwards.

## Mobile

~75% of traffic, so the compact view is the mobile-native one: four columns fit a phone
with no horizontal scroll, and the detail panel is a full-width stack that becomes a
two-column grid at `min-width: 641px`. Charts are inline SVG with a viewBox, so they
scale without a library. The root is a bounded 85svh panel with its own scrollbar.

## Search engines

`tool.html` ships with a real 32-row HTML table between the `SFA:PRELOAD` markers,
holding unfiltered season totals. Refresh it with:

```
python scripts/pull_personnel_grouping.py
python scripts/refresh_preload.py
```

then re-paste `tool.html` into Avada.

## Before shipping a change

```
python scripts/lint_embed.py tools/personnel-grouping-compact/tool.html
```
