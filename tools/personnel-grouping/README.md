# Personnel Grouping Frequency

The shipped tool. Merges the full grid's layout with the compact version's team detail,
and adds efficiency.

- **Fragment:** `tool.html` — paste the whole file into an Avada custom code block.
- **Data:** `data/personnel_grouping_<season>.json`, listed by `data/personnel_grouping_index.json`.
- **Root class:** `.pt-root.pt-pg`. All CSS is scoped to it.

Supersedes `personnel-grouping-full/` and `personnel-grouping-compact/`, which are kept
only so this can be diffed against them. Delete both once you're happy.

## Table

`# · Offense · 11 · 12 · 13 · 21 · 22 ‖ 2+ TE · 2+ RB · 3+ WR · Plays`

The five groupings cover ~97% of plays; the rest (10, 20, 23, 01 and so on) are left out
of the table by design and still appear in the team detail panel. Rows therefore do not
total 100%.

The three columns after the divider overlap on purpose — a 2-RB, 2-TE snap counts in both
2+ TE and 2+ RB. They are three independent questions, not shares of a whole, so a row
does not total 100% across them. They render identically to the grouping columns, with the
3px rule carrying the separation; the League row at the foot of the table gives the league
average for each.

The rank column is a shaded gutter down the left, and follows the current sort, so sorting by 2+ TE renumbers 1–32. Sorted
alphabetically it falls back to total plays. Default sort is 11 personnel, descending.

## Usage / Efficiency toggle

Top right. **Usage** shows each grouping as a share of the offense's plays.
**Efficiency** swaps every cell to EPA per play, shaded on a diverging scale — slate below
zero, Sharp red above. Sorting persists across the switch, so if you're sorted by 12
personnel you stay sorted by 12, just by a different metric.

## Hover / tap

Any cell gives EPA per play, yards per play and success rate, each with a league rank.
Hover on desktop, tap on touch — gated on `pointerType` rather than screen width, because
a tap otherwise synthesises a mouseenter immediately before the click and the panel would
open and shut in one gesture.

Ranks are computed **among offenses clearing the 20-play minimum under the current
filters**, so heavy filtering can produce "3rd of 19" rather than "of 32". The panel says
so when the pool is short.

## The 20-play minimum

Below 20 matching plays a cell shows a dash in efficiency mode rather than a number, and
the hover explains why. Eight snaps of 22 personnel can read +0.9 EPA and look elite. The
usage percentage is always shown regardless — sample size only gates efficiency.

## Filters

Always visible as buttons showing their current value; clicking one opens a popover with
the options. Season, week, quarter, down, field zone and the RB/TE/WR counts are
multi-select; yards to go and score margin are dual ranges; play type is dropback or
designed run. Each popover has its own Reset, and **Clear all** resets everything.

**Neutral script** sets quarters 1–3 and margin within 14 points, and releases if you
touch either afterwards, so the buttons never misreport what's applied.

Popovers are absolutely positioned inside `.pt-root` and clamped to its width —
`position: fixed` would escape the Avada container.

## Team detail

Tap an offense for personnel mix (donut), week by week (three lines, applying every filter
except week), and grouping breakdown against league average — three cards on one row at
`min-width: 641px`, stacking below that. The donut is capped at 148px so it can't stretch
to fill its column.

## Height

Uses the house pattern, with fallbacks for browsers without `svh`:

```css
max-height: 1000px;
max-height: clamp(1000px, 120vh, 1320px);
max-height: clamp(1000px, 120svh, 1320px);
```

## Search engines

Ships a 32-row static table between the `SFA:PRELOAD` markers. Refresh with:

```
python scripts/pull_personnel_grouping.py
python scripts/refresh_preload.py
```

then re-paste `tool.html` into Avada.

## Before shipping a change

```
python scripts/lint_embed.py tools/personnel-grouping/tool.html
```
