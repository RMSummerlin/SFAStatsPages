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
├── .gitattributes                  ← `* text=auto`, stops Windows CRLF churn
├── .nojekyll                       ← keep it: Jekyll mangles {{ }} in .md files
├── docs/
│   ├── avada-embed-rules.md        ← constraints for building embeds (see below)
│   ├── tool-checklist.md           ← end-to-end steps for adding a tool
│   ├── personnel-grouping-data.md  ← data decisions behind the personnel tool
│   └── pace-data.md                ← data decisions behind the pace tool
├── data/                           ← generated JSON + preload tables, served via Pages
├── scripts/
│   ├── config.py                   ← season → Google Sheet ID map, team aliases, names
│   ├── requirements.txt
│   ├── pull_personnel_grouping.py  ← pull + transform (auto-run by the workflow)
│   ├── pull_pace.py                ← pull + transform (auto-run by the workflow)
│   ├── test_pace.py                ← regression tests (auto-run by the workflow)
│   ├── test_dead_ball.py           ← regression tests (auto-run by the workflow)
│   ├── test_teams.py               ← regression tests (auto-run by the workflow)
│   ├── test_empty_season.py        ← regression tests (auto-run by the workflow)
│   ├── lint_embed.py               ← checks a fragment against the embed rules
│   ├── build_embed.py              ← strips the dev notes to produce embed.html
│   └── preloads.py                 ← folds each tool's preload table into preloads.json
├── index.html                      ← endpoint health check, served at the Pages root
├── tools/
│   ├── personnel-grouping/         ← tool.html + embed.html + README.md
│   └── pace/                       ← tool.html + embed.html + README.md
├── wordpress/
│   ├── sfa-preloads.php            ← Code Snippets body: shortcodes for the crawlable tables
│   └── README.md                   ← install, caching and refresh schedule
└── .github/
    └── workflows/
        └── update-data.yml         ← scheduled Action that runs the Python pipeline
```

Anything named `pull_*.py` is picked up and run automatically by the workflow, and
anything named `test_*.py` is run as a test before the pulls. Helper scripts are
deliberately named otherwise so they stay manual.

## Two files per tool

Each tool folder holds the same fragment twice:

- **`tool.html`** — the working copy, carrying every note about why the code does what it
  does. This is the one to edit.
- **`embed.html`** — the same fragment with all comments removed. **This is the one that
  goes into Avada.** Anyone can hit Ctrl+U on a published article, so the development
  notes should not be there.

`python scripts/build_embed.py` regenerates `embed.html` from `tool.html`; it removes
comments and nothing else, so a diff between the two files is deletions only. It refuses
to write if the result fails to parse, if any non-comment character moved, or if a URL or
string literal changed. `--check` reports a stale `embed.html` without writing one.

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
python scripts/pull_pace.py

# or from a downloaded CSV export, without touching the sheet
python scripts/pull_personnel_grouping.py --csv ~/Downloads/export.csv --season 2025
python scripts/pull_pace.py --csv ~/Downloads/export.csv --season 2025

# run the regression tests the workflow runs before every pull
python scripts/test_pace.py
python scripts/test_dead_ball.py

# regenerate the paste-ready embed.html for every tool
python scripts/build_embed.py

# check the fragments against the embed rules
python scripts/lint_embed.py
```

## Status

Two tools shipped:

- **`tools/personnel-grouping/`** — personnel grouping frequency with a usage/efficiency
  toggle and EPA per play, yards per play and success rate on hover. 2021 through 2025.
- **`tools/pace/`** — offensive tempo and play volume, with a Tempo/Volume toggle,
  a neutral-situation column and a gear-change column. Data decisions in
  [`docs/pace-data.md`](docs/pace-data.md).

The pace tool only offers seasons whose sheet carries the `TimeSinceSnap` column. Run the
workflow with **Rebuild every season** ticked and read the log to find out which those are:
any season without it prints a warning and is left out of `data/pace_index.json`.
