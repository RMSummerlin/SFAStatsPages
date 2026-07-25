# tools/

Each embeddable tool lives in its own subfolder here, named for the tool itself (e.g. `tools/qb-stat-leaders/`).

A typical tool folder contains:

```
tools/example-tool-name/
├── tool.html      ← the finished fragment (style + .pt-root div + script) pasted into Avada's custom code block
├── README.md      ← what the tool does, its data source, and embed instructions
└── src/           ← optional: separate style.css / script.js if built outside a single file first
```

Every tool must follow the constraints in `docs/avada-embed-rules.md` before it ships.

No tools have been built yet — this file exists to establish the convention ahead of the first one.
