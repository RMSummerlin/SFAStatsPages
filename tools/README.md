# tools/

Each embeddable tool lives in its own subfolder here, named for the tool itself.

A typical tool folder contains:

```
tools/example-tool-name/
├── tool.html      ← the working fragment (style + .pt-root div + script), with all the development notes
├── embed.html     ← the same fragment with every comment stripped — THIS is the one to paste into Avada
└── README.md      ← what the tool does, its data source, and embed instructions
```

`embed.html` is generated, never hand-edited. Change `tool.html`, then run
`python scripts/build_embed.py` to rebuild it. The two differ by deleted comments and
nothing else, so anything reproducible in one is reproducible in the other.

Every tool must follow the constraints in `docs/avada-embed-rules.md`. Check it
mechanically rather than by eye:

```
python scripts/lint_embed.py
```

Lint reads every `tools/*/*.html`, so both copies of each fragment are checked.

Each tool's root element carries its own class alongside `.pt-root` (e.g.
`.pt-root.pt-pgf`) and scopes all of its CSS to that pair, so several tools can be
previewed on the same page without their styles colliding.

## Built so far

| Folder | What it is |
|--------|------------|
| `personnel-grouping/` | Fixed 11/12/13/21/22 columns plus 2+ TE / 2+ RB / 3+ WR, a usage/efficiency toggle, and EPA / yards / success rate on hover |
| `pace/` | Offensive tempo and play volume, with a Tempo/Volume toggle, a neutral-situation column and a gear-change column |
| `matchup/` | One game at a time: offense vs defense ranks in five battles with the edge drawn between them, a week stepper, a slate picker and a detail sheet |
| `boxscore/` | One played game at a time: the scoreline, seven diverging bars showing which team was better in each category, and an offensive box score in four groups with season averages |
| `proe/` | Pass rate over expected: offense and defense tables with a last-four column, a week filter and pooled seasons, an 18-week chart per team, and a matchups tab pairing each offense with the defense it faces |
| `redzone/` | Red zone targets, carries and touchdowns by player with an inside-20 / 10 / 5 toggle, position pills, shares of the team's red zone work, a Teams tab for one offense's usage and a Leaders tab of pre-sorted boards |
| `redzone-team/` | Red zone offense and defense efficiency: trips, TD %, scoring %, points per trip, EPA and success inside the 20, goal-to-go and inside-10 TD %, with a rank badge under every figure and a trips-by-week chart |

## The Weeks filter

Five tools (personnel grouping, pace, PROE and both red zone tools) filter by week, and
all five share one picker so a reader learns it once. The popover opens with a pair of
native selects, reading Week 1 to Week 18 until something is picked, over a grid of 18
week chips. Choosing either end paints every week between them, the second list starts
at whatever the first says, and each chip then toggles one week, so "weeks 3 to 7
without the week 5 game he missed" is two picks and one tap. Every change applies as it
is made; Done only closes the popover. Nothing picked, or every week picked, reads as All. The chip
shows the picks as runs (`Weeks 3–4, 6–7`) and falls back to a count past three runs;
the two red zone tools write the same runs into the hash (`#w3-4,6-7`). The list is
always the full 18 weeks whichever seasons are pooled, so a prior season's weeks can
be picked while the current one is loaded, and the pick survives a season change.
