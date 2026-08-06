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
| `personnel-grouping/` | Fixed 11/12/13/21/22 columns plus 2+ TE / 2+ RB / 3+ WR, a usage/efficiency toggle, and EPA / yards / success rate on hover |
