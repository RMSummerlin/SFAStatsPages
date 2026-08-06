# SFAStatsPages

Embeddable HTML/CSS/JS stat tools for Sharp Football Analysis, built for the Avada (WordPress) page builder. Data is pulled from a restricted Google Sheet, processed by Python, and published as static JSON via GitHub Pages for the embedded tools to fetch.

## Pipeline overview

```
Google Sheet (restricted, CSV export)   — one sheet per season,
        |                                  read via a service account
        ↓
Python scripts (scripts/)  — run on a schedule via GitHub Actions
        ↓
Static JSON (data/)  — committed back to the repo
        ↓
GitHub Pages  — serves data/ as static files
        ↓
Embedded JS on Avada  — fetch()'s the JSON, renders the tool
```

Sheet access: the season sheets are Restricted. A Google service account has Viewer
access and its key is stored in the repo secret `GOOGLE_SERVICE_ACCOUNT_JSON`. See
`docs/tool-checklist.md` section 4.

Update cadence: checked every 30 minutes, all week (actual source data changes ~3x/week on a variable schedule, so we poll frequently and only commit when something changes).

## Repo structure

```
SFAStatsPages/
├── README.md
├── docs/
│   ├── avada-embed-rules.md        ← constraints for building embeds (see below)
│   ├── tool-checklist.md           ← end-to-end steps for adding a tool
│   └── personnel-grouping-data.md  ← data decisions behind the personnel tools
├── data/                           ← generated JSON, served via GitHub Pages
├── scripts/
│   ├── config.py                   ← season → Google Sheet ID map
│   ├── requirements.txt
│   ├── pull_personnel_grouping.py  ← pull + transform (auto-run by the workflow)
│   ├── lint_embed.py               ← checks a fragment against the embed rules
│   └── refresh_preload.py          ← injects the crawlable static table into tools
├── index.html                      ← endpoint health check, served at the Pages root
├── tools/
│   ├── personnel-grouping/         ← the shipped tool
│   ├── personnel-grouping-full/    ← superseded layout option A
│   └── personnel-grouping-compact/ ← superseded layout option B
└── .github/
    └── workflows/
        └── update-data.yml         ← scheduled Action that runs the Python pipeline
```

Anything named `pull_*.py` is picked up and run automatically by the workflow. Helper
scripts are deliberately named otherwise so they stay manual.

## Embedding rules (summary — full detail in docs/avada-embed-rules.md)

- Deliver a fragment only: one `<style>` block, one root `<div class="pt-root">`, one `<script>`. No `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<meta>`, `<title>`.
- Scope every CSS selector under `.pt-root` — never bare `*`, `body`, `header`, `input`, etc. Give each tool its own root class too (e.g. `.pt-root.pt-pgf`) so two tools can share a page.
- No semantic landmark elements (`<header>`, `<footer>`, `<nav>`, `<main>`, `<section>`) — use prefixed divs like `.pt-header`.
- No `position: fixed` for in-flow UI (only for intentional full-screen modals).
- Long scrollable lists get their own bounded scroll panel, not page-level scroll.
- Brand font: Interstate Condensed (self-hosted).
- Brand colors: black `#000`, Sharp red `#cc0000`, backgrounds `#f4f5f7` / `#fff` / `#f9fafb`, text `#111`, grays `#7f8c9a` / `#b0bec5`, borders `#cdd5de` / `#dde2e8`.
- Audience is ~75% mobile — design mobile-first, enhance at `min-width: 641px`.

Run `python scripts/lint_embed.py` to check every tool against these mechanically.

## Local development

```
# rebuild data from the live sheet
python scripts/pull_personnel_grouping.py

# or from a downloaded CSV export, without touching the sheet
python scripts/pull_personnel_grouping.py --csv ~/Downloads/export.csv --season 2025

# refresh the crawlable static tables inside the tool fragments
python scripts/refresh_preload.py

# check the fragments against the embed rules
python scripts/lint_embed.py
```

## Status

First tool shipped: **`tools/personnel-grouping/`** — personnel grouping frequency with a
usage/efficiency toggle and EPA per play, yards per play and success rate on hover.

The two earlier layout options (`personnel-grouping-full`, `personnel-grouping-compact`)
are kept for diffing and can be deleted once the shipped version is settled.

2025 is the only season loaded so far; add earlier seasons to `SEASON_SHEETS` in
`scripts/config.py` when their sheets exist.
