# SFAStatsPages

Embeddable HTML/CSS/JS stat tools for Sharp Football Analysis, built for the Avada (WordPress) page builder. Data is pulled from a public Google Sheet, processed by Python, and published as static JSON via GitHub Pages for the embedded tools to fetch.

## Pipeline overview

```
Google Sheet (public, CSV export)
        ↓
Python scripts (scripts/)  — run on a schedule via GitHub Actions
        ↓
Static JSON (data/)  — committed back to the repo
        ↓
GitHub Pages  — serves data/ as static files
        ↓
Embedded JS on Avada  — fetch()'s the JSON, renders the tool
```

Update cadence: checked every 30 minutes, all week (actual source data changes ~3x/week on a variable schedule, so we poll frequently and only commit when something changes).

## Repo structure

```
SFAStatsPages/
├── README.md
├── docs/
│   └── avada-embed-rules.md   ← constraints for building embeds (see below)
├── data/                       ← generated JSON, served via GitHub Pages
├── scripts/                    ← Python scripts that pull/transform sheet data
├── tools/
│   └── example-tool-name/
│       ├── tool.html           ← full fragment pasted into Avada's custom code block
│       └── README.md           ← what it does, data source, embed instructions
└── .github/
    └── workflows/
        └── update-data.yml     ← scheduled Action that runs the Python pipeline
```

## Embedding rules (summary — full detail in docs/avada-embed-rules.md)

- Deliver a fragment only: one `<style>` block, one root `<div class="pt-root">`, one `<script>`. No `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<meta>`, `<title>`.
- Scope every CSS selector under `.pt-root` — never bare `*`, `body`, `header`, `input`, etc.
- No semantic landmark elements (`<header>`, `<footer>`, `<nav>`, `<main>`, `<section>`) — use prefixed divs like `.pt-header`.
- No `position: fixed` for in-flow UI (only for intentional full-screen modals).
- Long scrollable lists get their own bounded scroll panel, not page-level scroll.
- Brand font: Interstate Condensed (self-hosted).
- Brand colors: black `#000`, Sharp red `#cc0000`, backgrounds `#f4f5f7` / `#fff` / `#f9fafb`, text `#111`, grays `#7f8c9a` / `#b0bec5`, borders `#cdd5de` / `#dde2e8`.
- Audience is ~75% mobile — design mobile-first, enhance at `min-width: 641px`.

## Status

Repo setup in progress. No tools built yet.
