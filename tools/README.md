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
