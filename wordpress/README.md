# wordpress/

Server-side rendering for the crawlable stat tables.

Without this, each tool ships a static table baked into its `tool.html`, which only
refreshes when the fragment is re-pasted into Avada. With this, the table is fetched
server-side and stays current on its own.

## What's here

`sfa-preloads.php` — paste into **Code Snippets** (set to run everywhere) or the child
theme's `functions.php`. No configuration.

It registers one shortcode per tool:

| Shortcode | Table |
|-----------|-------|
| `[sharp_football_personnel]` | Personnel grouping frequency |
| `[sharp_football_pace]` | Offensive pace |

## How it works

`scripts/preloads.py` collects every tool's `data/<tool>_preload.html` into
`data/preloads.json` on each pipeline run — one file, about 2 KB gzipped. The snippet
fetches that manifest once and caches it, so **the number of shortcodes on a page does not
affect the number of requests**, and the cache is shared across pages too.

Distinct shortcodes are deliberate: they read clearly in the CMS. They all share the same
cached manifest underneath.

Three things worth knowing about the caching:

- **A transient is the live cache; an option holds the last known good copy.** If GitHub
  is briefly unreachable when the transient expires, the last good table is served and the
  retry is deferred two minutes, rather than an empty table appearing on a live article
  and every subsequent page view hammering a failing endpoint. Same shape as the injury
  report snippet, which has been running in production.
- **Failures go to `error_log`** with the reason and the URL, so a silent stale table is
  diagnosable rather than mysterious.
- **The HTML is sanitised once at fetch time, not per render.** `wp_kses` is regex-heavy
  and the result is identical every time.
- **A lock stops a stampede.** When the cache expires, concurrent requests would all try to
  refresh. One takes a short lock and the rest serve stale for a second.
- **`wp_kses` runs against a table-only whitelist**, not `wp_kses_post`. The content is
  ours and arrives over HTTPS, but it is still remote HTML echoed into every article, and a
  whitelist of table tags means nothing executable could reach the page even if the source
  were tampered with. Verified against the actual generated tables, so nothing is silently
  stripped.

## Cache window

The tables refresh **once a week, at 23:00 Eastern on Tuesday** — set by
`SFA_PRELOAD_REFRESH_DAY` and `SFA_PRELOAD_REFRESH_TIME`. The sheets are only topped up
once a week and almost always on a Tuesday, so anything more frequent spends a blocking
HTTP request on a file that has not changed.

It is anchored to a wall-clock moment rather than a rolling seven days, so the cache always
turns over just after the week's data has landed instead of drifting by however long ago
the last page view happened to be. DST is handled by `DateTimeZone`, so the boundary stays
at 23:00 local across the November and March changes.

Two consequences worth knowing:

- **The interactive tools are unaffected.** They fetch their own JSON client-side on every
  page load, so the numbers a reader sees are always current. This schedule governs only
  the crawlable snapshot.
- **If you upload data on some other day**, the snapshot waits until the following Tuesday.
  Load any page carrying a shortcode with `?sfa_refresh=1` while logged in as an editor to
  pick it up immediately.

A failed fetch is separate from this schedule: it serves the last good copy and retries
after two minutes (`SFA_PRELOAD_RETRY`) rather than waiting a week.

## Adding a tool

1. The pull script writes `data/<tool>_preload.html` as it already does.
2. `preloads.py` picks it up automatically — no edit needed.
3. Add one `add_shortcode(...)` line at the bottom of the snippet, matching the key in
   `data/preloads.json`.
4. Add `hideServerPreload()` to the new tool's render path, copying either existing tool.

## If Code Snippets is ever removed

Nothing breaks in a visible way — the shortcodes stop resolving and the tables disappear
from the raw HTML, but the interactive tools are unaffected because they fetch their own
data. To go back to baked-in tables, run `python scripts/refresh_preload.py` and re-paste.
