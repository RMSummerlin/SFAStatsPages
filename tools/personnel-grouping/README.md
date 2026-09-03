# Personnel Grouping Frequency

The shipped tool. Merges the full grid's layout with the compact version's team detail,
and adds efficiency.

- **Fragment:** `tool.html` — paste the whole file into an Avada custom code block.
- **Data:** `data/personnel_grouping_<season>.json`, listed by `data/personnel_grouping_index.json`.
- **Root class:** `.pt-root.pt-pg`. All CSS is scoped to it.

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

The rank column is a shaded gutter down the left. It means "position when this column is
ordered best first", so sorting ascending reverses the row order without renumbering —
the worst 11-personnel team reads 32 whether it appears at the top or the bottom. Ties
share a rank. It follows the current sort, so sorting by 2+ TE renumbers 1–32. Sorted
alphabetically it falls back to total plays. Default sort is 11 personnel, descending.

## Usage / Efficiency toggle

Top right. **Usage** shows each grouping as a share of the offense's plays.
**Efficiency** swaps every cell to EPA per play, shaded on a diverging scale — slate below
zero, Sharp red above. Sorting persists across the switch, so if you're sorted by 12
personnel you stay sorted by 12, just by a different metric.

## Grouping descriptions

Hovering a column header gives the personnel for that grouping — `12` is "1 RB, 2 TE,
2 WR", nothing more. Hover is mouse-only, so **What do the groupings mean?** in the footer
expands the same list inline for touch users, with a single footnote there (rather than in
every tooltip) noting that six-lineman looks are folded in and run one receiver lighter.

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
`min-width: 641px`, stacking below that.

All three charts share a single 300×180 viewBox, and each one's SVG, legend and caption sit
inside a `.pt-chart` block capped at 460px and centred as a unit. Capping the SVG alone
was a bug: the chart centred itself while the legend stayed full-width, so the two only
lined up when the column happened to match the cap. Charts fill the column on ordinary
screens and stop growing on an ultrawide.

The league comparison is a vertical bar chart — groupings across the X axis, share of plays
up the Y, the gap to league on top of each bar in grey, and a dashed connector to the
league tick when an offense is well clear of average. The gap sits above the value
deliberately understated — colouring it competed with the percentage it annotates. Groupings with fewer than five snaps are dropped
rather than given a bar reading 0%. Codes are zero-padded, so 0 RB / 2 TE reads `02`.

## Height

Uses the house pattern, with fallbacks for browsers without `svh`:

```css
max-height: 1000px;
max-height: clamp(1000px, 120vh, 1320px);
max-height: clamp(1000px, 120svh, 1320px);
```

## Which file to paste

`embed.html`, not `tool.html`. Same fragment, comments removed, regenerated by
`python scripts/build_embed.py`. Edit `tool.html`; never edit `embed.html` by hand.

## Search engines

The crawlable 32-row table is rendered on the article by the
`[sharp_football_personnel]` shortcode, not by this fragment.
`pull_personnel_grouping.py` regenerates `data/personnel_grouping_preload.html` on
every pull and `preloads.py` folds it into `data/preloads.json`; WordPress re-fetches
that manifest weekly. Nothing here needs re-pasting when the data changes — see
`wordpress/README.md`.

## Before shipping a change

```
python scripts/lint_embed.py tools/personnel-grouping/tool.html
```
