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

Other inputs: the matchup tool reads two things that are not the sheet — nflverse
`games.csv` (from `raw.githubusercontent.com`, fetched every run and cached to
`data/schedule_<season>.json`) and `data/offseason_changes_<season>.json`, which
`scripts/offseason_changes.py` drafts once a year from nflverse plus the Wikipedia
coordinator navboxes and an editor then corrects by hand. Both are covered in
[`docs/matchup-data.md`](docs/matchup-data.md). So a scheduled run needs outbound access to
Google *and* GitHub; the annual `offseason_changes.py` run additionally needs Wikipedia.

## Repo structure

```
SFAStatsPages/
├── README.md
├── .gitattributes                  ← `* text=auto`, stops Windows CRLF churn
├── .gitignore                      ← Python bytecode, .venv, and a guard against a stray key file
├── .nojekyll                       ← keep it: Jekyll mangles {{ }} in .md files
├── docs/
│   ├── avada-embed-rules.md        ← constraints for building embeds (see below)
│   ├── tool-checklist.md           ← end-to-end steps for adding a tool
│   ├── personnel-grouping-data.md  ← data decisions behind the personnel tool
│   ├── pace-data.md                ← data decisions behind the pace tool
│   ├── matchup-data.md             ← data decisions and backtest behind the matchup tool
│   └── matchup-talking-points.md   ← page copy and method explanations for the matchup article
├── data/                           ← served via Pages: generated JSON and preload tables,
│                                     plus two caches and one hand-corrected input (see below)
├── scripts/
│   ├── config.py                   ← season → Google Sheet ID map, team aliases, names
│   ├── offense.py                  ← folds a play-logged-twice sheet to the offense's rows (see below)
│   ├── requirements.txt
│   ├── pull_personnel_grouping.py  ← pull + transform (auto-run by the workflow)
│   ├── pull_pace.py                ← pull + transform (auto-run by the workflow)
│   ├── pull_matchup.py             ← pull + transform (auto-run by the workflow)
│   ├── offseason_changes.py        ← drafts data/offseason_changes_<season>.json once a year (never on the schedule)
│   ├── test_pace.py                ← regression tests (auto-run by the workflow)
│   ├── test_offense.py             ← regression tests (auto-run by the workflow)
│   ├── test_dead_ball.py           ← regression tests (auto-run by the workflow)
│   ├── test_teams.py               ← regression tests (auto-run by the workflow)
│   ├── test_empty_season.py        ← regression tests (auto-run by the workflow)
│   ├── test_matchup.py             ← regression tests (auto-run by the workflow)
│   ├── lint_embed.py               ← checks a fragment against the embed rules
│   ├── build_embed.py              ← strips the dev notes to produce embed.html
│   └── preloads.py                 ← folds each tool's preload table into preloads.json
├── index.html                      ← endpoint health check, served at the Pages root
│                                     (https://rmsummerlin.github.io/SFAStatsPages/)
├── tools/
│   ├── personnel-grouping/         ← tool.html + embed.html + README.md
│   ├── pace/                       ← tool.html + embed.html + README.md
│   └── matchup/                    ← tool.html + embed.html + README.md
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

### Sheets that log every play twice

From 2026 the provider's export carries each play on two rows, one per team, with
`team`/`opponent` swapped and the perspective columns (HomeRoad, ScoreDiff, scores,
timeouts) flipped — and nothing on either row saying which is the offense. The
2021–2025 sheets had one row per play with `team` meaning the offense, which is what
every pull script assumes. Each script therefore passes its rows through
`offense.offense_rows()` right after reading them; it infers the offense from shared
player IDs across drives, the yard line in the play description, and drive
alternation, keeps that copy, merges the one-sided flag columns onto it, and prints
one line saying how many drives each signal decided. A sheet that is not mirrored
passes through untouched, apart from a guard: because the export has no offense
marker, a one-row-per-play sheet is spot-checked the same way, and the pull stops if
the descriptions say the rows are the defense's copy. Full reasoning in the module's
docstring; regression fixture in `scripts/test_offense.py`.

### What's in `data/`

Not everything under `data/` is generated output, and the three kinds behave very
differently if one goes missing:

| File | Kind | If you delete it |
|---|---|---|
| `<tool>_<season>.json`, `<tool>_index.json` | output | Rebuilt by the next pull. |
| `<tool>_preload.html`, `preloads.json` | output | Rebuilt by the next pull, via `preloads.write_manifest()`. |
| `schedule_<season>.json` | cache of nflverse `games.csv` | Re-fetched next run. It exists so one bad fetch does not take the matchup tool down. |
| `matchup_prior_<season>.json` | cache of last season's per-team totals | Re-read from the prior season's ~16 MB sheet — which is the reason it is cached. Force a re-read with `--refresh-prior`. |
| `offseason_changes_<season>.json` | **hand-corrected input** | Not regenerated on the schedule. `pull_matchup.py` prints a warning and applies no QB or coaching haircuts, which silently changes every rating it publishes. Redraft with `scripts/offseason_changes.py` and review it by hand again. |

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

## Getting set up

CI runs Python 3.12 (pinned in `.github/workflows/update-data.yml`); 3.11 runs the full
test suite locally without complaint.

```
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
```

The install is only needed to read a **private** sheet. `google-auth` and `requests` are
imported lazily and only on that path — every pull script runs on the standard library
alone when it is working from a `--csv` export or a link-shared sheet, which is how local
work normally goes. The service account key is not needed locally and should not be on
your machine; see `docs/tool-checklist.md` section 4.

## Local development

```
# --- rebuild data from the live sheet ---
python scripts/pull_personnel_grouping.py
python scripts/pull_pace.py
python scripts/pull_matchup.py

# --- or from a downloaded CSV export, without touching the sheet ---
python scripts/pull_personnel_grouping.py --csv ~/Downloads/export.csv --season 2025
python scripts/pull_pace.py --csv ~/Downloads/export.csv --season 2025
python scripts/pull_matchup.py --csv cur.csv --prior-csv prev.csv --season 2026 \
    --schedule data/schedule_2026.json     # fully offline: no sheet, no nflverse fetch

# every season in config.py rather than just the current one
python scripts/pull_pace.py --all

# --- the regression tests, all of which the workflow runs before any pull ---
python scripts/test_pace.py
python scripts/test_dead_ball.py
python scripts/test_teams.py
python scripts/test_empty_season.py
python scripts/test_matchup.py

# --- embeds ---
python scripts/build_embed.py            # regenerate every embed.html from its tool.html
python scripts/build_embed.py --check    # report a stale embed.html without writing one
python scripts/lint_embed.py             # check both copies against the embed rules

# --- annual, and deliberately never run on the schedule ---
python scripts/offseason_changes.py --season 2026    # drafts a file to correct by hand
```

### Previewing a tool

`tool.html` is a fragment on purpose — no `<!DOCTYPE>`, no `<html>` — so there is no page
to open. Serve the repo and open the fragment directly:

```
python -m http.server 8000
# then http://localhost:8000/tools/pace/tool.html
```

Two things to know before trusting what you see:

- **It renders in quirks mode.** With no doctype the browser is not in the standards mode
  Avada gives it. Each tool resets `box-sizing` under its own root so most of the layout
  holds, but treat spacing as approximate. An Avada staging page is still the only real
  check — `docs/tool-checklist.md` section 6.
- **It shows published data, not yours.** Every fragment hardcodes
  `var BASE = 'https://rmsummerlin.github.io/SFAStatsPages/data/'`, so a pull you just ran
  locally is invisible until it is committed and Pages has rebuilt. To preview against
  local JSON, point `BASE` at `http://localhost:8000/data/` while you work — and don't
  commit that line.

## Status

Three tools shipped:

- **`tools/personnel-grouping/`** — personnel grouping frequency with a usage/efficiency
  toggle and EPA per play, yards per play and success rate on hover. 2021 through 2025.
- **`tools/pace/`** — offensive tempo and play volume, with a Tempo/Volume toggle,
  a neutral-situation column and a gear-change column. Data decisions in
  [`docs/pace-data.md`](docs/pace-data.md).
- **`tools/matchup/`** — one game at a time: offense against the defense it faces in five
  battles, with a week stepper, a slate picker and a detail sheet. Data decisions and the
  backtest behind the blend in [`docs/matchup-data.md`](docs/matchup-data.md); the copy
  that runs around it in
  [`docs/matchup-talking-points.md`](docs/matchup-talking-points.md).

The pace tool only offers seasons whose sheet carries the `TimeSinceSnap` column. Run the
workflow with **Rebuild every season** ticked and read the log to find out which those are:
any season without it prints a warning and is left out of `data/pace_index.json`.
