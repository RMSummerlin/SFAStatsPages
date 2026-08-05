# tools/

Each embeddable tool lives in its own subfolder here, named for the tool itself.

A typical tool folder contains:

```
tools/example-tool-name/
├── tool.html      ← the finished fragment (style + .pt-root div + script) pasted into Avada's custom code block
├── README.md      ← what the tool does, its data source, and embed instructions
└── src/           ← optional: separate style.css / script.js if built outside a single file first
```

Every tool must follow the constraints in `docs/avada-embed-rules.md`. Check it
mechanically rather than by eye:

```
python scripts/lint_embed.py
```

Each tool's root element carries its own class alongside `.pt-root` (e.g.
`.pt-root.pt-pgf`) and scopes all of its CSS to that pair, so several tools can be
previewed on the same page without their styles colliding.

## Built so far

| Folder | What it is |
|--------|------------|
| `personnel-grouping-full/` | Personnel grouping frequency as an offense × grouping grid, heat-shaded — closest to the old Tableau dashboard |
| `personnel-grouping-compact/` | Same data as three columns (2+ RB / 2+ TE / 3+ WR) with a per-team slide-out containing charts |

These two are competing layouts for the same tool, built so the layout call can be made
against something real. Both read the same JSON, so retiring one costs nothing.
