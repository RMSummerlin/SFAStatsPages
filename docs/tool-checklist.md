# New Tool Checklist

Steps to follow whenever a new tool is added to this repo.

## 1. Data pipeline (if the tool needs new/different data)

All tools pull from the same public Google Sheet, but each may need different columns, tabs, or transformations. The workflow auto-discovers and runs any script matching `scripts/pull_*.py` — no changes to `.github/workflows/update-data.yml` are needed for a normal new tool.

- [ ] Name the new pull script `scripts/pull_<tool-or-data-name>.py` (must match the `pull_*.py` pattern to be picked up automatically)
- [ ] Script reads from the shared Google Sheet (CSV export URL) and writes its own output to `data/<tool-or-data-name>.json`
- [ ] If the script needs a **new Python package**, add it to `scripts/requirements.txt`
- [ ] Test the script locally before committing — confirm it produces valid JSON in `data/`
- [ ] **Only touch `update-data.yml` directly if:** the schedule itself needs to change, the script needs to write outside `data/`, or something needs to run in a fundamentally different way than "pull → write JSON → commit if changed"

## 2. Tool build (HTML/CSS/JS fragment)

- [ ] New folder under `tools/<tool-name>/`
- [ ] `tool.html` — the finished fragment, following every rule in `docs/avada-embed-rules.md`
- [ ] `tools/<tool-name>/README.md` — what it does, which `data/*.json` file(s) it fetches, and any embed-specific notes
- [ ] Fetches data via the GitHub Pages URL, e.g. `fetch('https://<username>.github.io/SFAStatsPages/data/<tool-or-data-name>.json')`

## 3. Avada embed rules — quick check
(Full detail in `docs/avada-embed-rules.md`)

- [ ] Fragment only — no doc-level tags (`<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<meta>`, `<title>`)
- [ ] All CSS scoped under `.pt-root` — no bare `*`, `body`, `input`, etc.
- [ ] No semantic landmark elements (`<header>`, `<footer>`, `<nav>`, `<main>`, `<section>`) — use `.pt-` prefixed divs
- [ ] No `position: fixed` outside of an intentional full-screen modal
- [ ] Long/scrollable lists use the bounded flex-column + internal scroll pattern, not page-level scroll
- [ ] Brand font (Interstate Condensed) and brand colors applied
- [ ] Mobile layout designed and verified first, before desktop enhancement at `min-width: 641px`
- [ ] Tap targets ≥44x44px

## 4. Before calling it done

- [ ] Pull script runs cleanly and produces the expected JSON
- [ ] Tool fetches and renders that JSON correctly
- [ ] Tested inside an actual Avada custom code block on a staging page, not just standalone
- [ ] Confirmed whether `update-data.yml` needed any changes (usually: no)
