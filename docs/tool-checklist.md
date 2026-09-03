# New Tool Checklist

Steps to follow whenever a new tool is added to this repo.

## 1. Data pipeline (if the tool needs new/different data)

All tools pull from the **season Google Sheets** listed in `scripts/config.py`, but each
may need different columns, tabs, or transformations. The workflow auto-discovers and runs
any script matching `scripts/pull_*.py` — no changes to `.github/workflows/update-data.yml`
are needed for a normal new tool.

- [ ] Name the new pull script `scripts/pull_<tool-or-data-name>.py` (must match the `pull_*.py` pattern to be picked up automatically)
- [ ] Script imports from `scripts/config.py` rather than hardcoding a sheet URL — use `config.csv_url(season)` and `config.CURRENT_SEASON`
- [ ] Read columns **by header name**, never by position — new columns get appended to the right of these sheets over time
- [ ] Fail loudly if a required column is missing, rather than silently producing empty output
- [ ] Script writes its own output to `data/<tool-or-data-name>.json` (one file per season if the tool is season-aware)
- [ ] Compare against the existing file before writing so a 30-minute run with no new games produces no commit
- [ ] If the script needs a **new Python package**, add it to `scripts/requirements.txt`. Prefer the standard library — it keeps CI fast
- [ ] Test locally before committing. Pull scripts should take a `--csv` flag so they can run against a downloaded export without hitting the sheet
- [ ] **Only touch `update-data.yml` directly if:** the schedule itself needs to change, the script needs to write outside `data/`, or something needs to run in a fundamentally different way than "pull → write JSON → commit if changed"
- [ ] If the script supports multiple seasons, give it an `--all` flag. The workflow greps each script's `--help` and only passes `--all` to scripts that advertise it, so the "Rebuild every season" checkbox then works with no YAML change
- [ ] Add a `scripts/test_<name>.py` for anything the pull script gets subtly wrong — the workflow runs every `scripts/test_*.py` before the pull step, again with no YAML change

## 1b. Wiring that is NOT auto-discovered

The `pull_*.py` glob covers the pull itself. These three do not happen on their own, and forgetting them fails quietly rather than loudly:

- [ ] `wordpress/sfa-preloads.php` — add one function + `add_shortcode` pair matching the tool's key in `data/preloads.json`, or the crawlable table never reaches the page and search engines see an empty embed
- [ ] `index.html` — add the tool to the `TOOLS` array so its endpoints show on the status page
- [ ] `docs/<tool>-data.md` — write down the data decisions while the reasoning is fresh, and link it from the tool's README

Helper scripts that should *not* run on the schedule must not be named `pull_*` — that is
why the linter is `lint_embed.py` and the manifest builder is `preloads.py`.

## 2. Tool build (HTML/CSS/JS fragment)

- [ ] New folder under `tools/<tool-name>/`
- [ ] `tool.html` — the finished fragment, following every rule in `docs/avada-embed-rules.md`
- [ ] `tools/<tool-name>/README.md` — what it does, which `data/*.json` file(s) it fetches, and any embed-specific notes
- [ ] Fetches data via the GitHub Pages URL, e.g. `fetch('https://rmsummerlin.github.io/SFAStatsPages/data/<tool-or-data-name>.json')`
- [ ] Root element carries a tool-specific class alongside `.pt-root` (e.g. `.pt-root.pt-pgf`) and **every** CSS selector is scoped to it, so two tools can be previewed on one page without clashing
- [ ] Calls `hideServerPreload()` on its first render, so the shortcode's crawlable table is replaced by the live tool rather than left stacked above it
- [ ] `python scripts/build_embed.py` run, producing `tools/<tool-name>/embed.html` — the comment-free copy that actually goes into Avada

## 3. Avada embed rules — automated check

Run the linter instead of eyeballing it:

```
python scripts/lint_embed.py tools/<tool-name>/tool.html tools/<tool-name>/embed.html
```

Lint both files. They should never differ in any way the linter can see, and if they do,
the stripper has a bug.

It fails on document-level tags, semantic landmark elements, unscoped CSS selectors,
missing `font-family: inherit`, a missing brand font, browser storage APIs and anything
that looks like a credential. It warns on `position: fixed`, missing 44px tap targets, an
unbounded root panel, no `min-width: 641px` enhancement, off-brand colors and a fragment
that never hides the shortcode's preload table. Full detail in `docs/avada-embed-rules.md`.

- [ ] `lint_embed.py` passes with no failures, and every warning is understood
- [ ] Mobile layout designed and verified first, before desktop enhancement at `min-width: 641px`

## 4. Google Sheet access

The season sheets are **Restricted** — not link-shared. A Google service account has
Viewer access, and its key lives in the repo secret `GOOGLE_SERVICE_ACCOUNT_JSON`.
`.github/workflows/update-data.yml` passes that secret to every `pull_*.py` run, so a new
script inherits access with no extra work.

- [ ] New pull scripts read the sheet through `fetch_csv()` (or the same pattern), so they
      pick up the token automatically
- [ ] When creating a **new season's sheet**, share it with the service account address as
      a Viewer before the first run, or the pipeline will fail on a sign-in page
- [ ] For local testing use `--csv <path>` with a downloaded export. The key is not needed
      locally and should not be on your laptop
- [ ] If `GOOGLE_SERVICE_ACCOUNT_JSON` is absent the scripts fall back to reading the sheet
      anonymously, which only works if that sheet is link-shared. The run log states which
      mode it used — check it if data stops updating

Rotating the key: create a new key in Google Cloud, update the repo secret, run
`workflow_dispatch` to confirm green, then delete the old key. The service account holds no
project IAM role by design — its only power is what the sheets grant it.

## 5. Start of season (annual, not per-tool)

Play-by-play data lives in a **new Google Sheet each season** (not a new tab in an ongoing
sheet) to avoid Google Sheets' 10-million-cell-per-file limit and to keep each season as a
clean, frozen archive once it ends.

- [ ] Create a new Google Sheet for the upcoming season (e.g. "NFL PBP 2026")
- [ ] Confirm it's public / viewable the same way the prior season's sheet was
- [ ] **Add** the new season to `SEASON_SHEETS` in `scripts/config.py` — add, don't replace. `CURRENT_SEASON` is `max(SEASON_SHEETS)`, so the newest season becomes the default everywhere at once
- [ ] Leave the prior season's entry and its `data/*.json` in place — it's now a frozen archive. Scheduled runs only re-pull the current season
- [ ] Confirm all `pull_*.py` scripts still go through `config.csv_url(season)` (no hardcoded old ID) so this one edit updates every script
- [ ] Run a manual `workflow_dispatch` trigger after the change to confirm the pipeline pulls from the new sheet correctly before the season's first real game
- [ ] The new sheet can be added to `config.py` before it has any data in it. Each `pull_*.py` skips a season with no rows: no JSON written, no index entry, so the season simply does not appear in any picker until real data lands, and no further edit is needed on the day it does. `scripts/test_empty_season.py` guards this
- [ ] Confirm the new sheet's headers match the old one exactly. Empty is fine; *wrong* still fails the run loudly, which is the intended difference

Backfilling an old season works the same way: add it to `SEASON_SHEETS` (and
`SEASON_GIDS` if the sheet's play-by-play is not on the first tab — check the `gid=`
in its URL), then rebuild once.

Either run it locally:

```
python scripts/pull_personnel_grouping.py --all
```

or, with no local setup at all, trigger it from the Actions tab: **Update Stats Data**
-> **Run workflow** -> tick **Rebuild every season**. The workflow passes `--all` to any
pull script that advertises the flag, and commits the new JSON itself. Scheduled runs
always leave the box unticked, so archives are never rebuilt on a timer.

## 6. Before calling it done

- [ ] Pull script runs cleanly and produces the expected JSON
- [ ] Numbers spot-checked against the raw sheet, not just against the tool's own output
- [ ] Tool fetches and renders that JSON correctly
- [ ] `data/<tool>_preload.html` generated and folded into `data/preloads.json`, and the shortcode's table renders on the article with JavaScript disabled
- [ ] `python scripts/build_embed.py --check` is clean, so `embed.html` matches `tool.html`
- [ ] The copy pasted into Avada came from `embed.html`, not `tool.html`
- [ ] Tested inside an actual Avada custom code block on a staging page, not just standalone
- [ ] Tested at phone width first, then desktop
- [ ] Confirmed whether `update-data.yml` needed any changes (usually: no)
