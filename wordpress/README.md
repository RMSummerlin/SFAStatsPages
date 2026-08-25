# wordpress/

Server-side rendering for the crawlable stat tables.

Without this, each tool ships a static table baked into its `tool.html`, which only
refreshes when the fragment is re-pasted into Avada. With this, the table is fetched
server-side and stays current on its own.

## What's here

`sfa-preloads.php` — paste into **Code Snippets** as a **PHP (Functions)** snippet,
scope **Run everywhere**, omitting the opening `<?php` line. Code Snippets supplies
that itself. No other configuration.

It registers one shortcode per tool:

| Shortcode | Table |
|-----------|-------|
| `[sharp_football_personnel]` | Personnel grouping frequency |
| `[sharp_football_pace]` | Offensive pace |

Put the shortcode in an Avada **Text Block**, not a Code Block. Code Blocks output
their contents raw and never run `do_shortcode`.

## The two halves

The shortcode is only half the mechanism. The other half lives in each tool:

```js
var n = document.querySelectorAll('[data-sfa-preload="pace"]');
```

`hideServerPreload()` runs on the tool's first paint and hides the shortcode's table.
It has to use `document`, not a lookup scoped to the tool's root, because the
shortcode renders into a sibling element in Avada rather than a child of `.pt-root`.

If the tool's data fetch fails, `render()` never runs, `hideServerPreload()` is never
called, and the server-rendered table stays on the page. That is the intended
fallback, not an oversight.

## Structure constraints

Code Snippets evaluates snippet bodies rather than including them as files, so the
snippet deliberately avoids three things that behave differently under `eval()`:

- **No top-level `return`.** A guard clause that returns early exits the whole
  snippet, registering nothing, with no error and the snippet still showing as
  active.
- **No `define()`.** Configuration is a function returning an array, so the body is
  safe to evaluate more than once.
- **No closures as shortcode callbacks.** Named functions, matching the shape of the
  injury report snippet that has been running in production.

If a shortcode ever renders as literal `[bracket_text]` on the page, the shortcode was
not registered. Check in this order: snippet type is Functions and not Content; scope
is Run everywhere and not Run once; the shortcode sits in a Text Block. A quick probe:
add `add_shortcode('sfa_test', 'sfa_test_cb');` with a matching function returning a
fixed string, and see whether `[sfa_test]` resolves.

## Caching

- **A transient is the live cache; an option holds the last known good copy.** If
  GitHub is briefly unreachable when the transient expires, the last good table is
  served and the retry is deferred two minutes, rather than an empty table appearing
  on a live article and every page view hammering a failing endpoint.
- **Failures go to `error_log`** with the reason and the URL.
- **The HTML is sanitised once at fetch time, not per render.** `wp_kses` is
  regex-heavy and the result is identical every time.
- **A lock stops a stampede** when the cache expires: one request refreshes, the rest
  serve stale for a second.
- **`wp_kses` runs against a table-only whitelist**, not `wp_kses_post`. The content is
  ours and arrives over HTTPS, but it is still remote HTML echoed into every article,
  and a whitelist of table tags means nothing executable could reach the page even if
  the source were tampered with. Verified against the actual generated tables.
- **Styles are printed inline on first render**, scoped entirely under `.sfa-preload`.
  The tool fragment's own CSS is scoped under `.pt-root` and cannot reach the
  shortcode output, so without this the table would render unstyled.

## Cache window

The tables refresh **once a week, at 23:00 Eastern on Tuesday**, set in
`sfa_preload_config()`. The sheets are only topped up once a week and almost always on
a Tuesday, so anything more frequent spends a blocking HTTP request on a file that has
not changed.

It is anchored to a wall-clock moment rather than a rolling seven days, so the cache
turns over just after the week's data lands instead of drifting by however long ago the
last page view happened to be. DST is handled by `DateTimeZone`.

Two consequences:

- **The interactive tools are unaffected.** They fetch their own JSON client-side on
  every page load. This schedule governs only the crawlable snapshot.
- **If you upload data on some other day**, the snapshot waits until the following
  Tuesday. Load any page carrying a shortcode with `?sfa_refresh=1` while logged in as
  an editor to pick it up immediately.

A failed fetch is separate from this schedule: last good copy, retry after two minutes.

## One table or two

A page carrying the shortcode has two crawlable copies of the same table: the one the
shortcode renders, and the one baked into `tool.html` between the `SFA:PRELOAD`
markers. Pick one per article.

- **Keep both** (default). Duplicate table markup in the raw HTML. Harmless to
  readers, since the personnel tool's baked copy is inside `#pg-body` and gets wiped
  on render, and the pace tool's is visually hidden. It is a duplicate-content signal
  to crawlers, which is the thing the preload was built to manage in the first place.

Only strip for tools whose article actually carries the shortcode.

## Adding a tool

1. The pull script writes `data/<tool>_preload.html` as it already does.
2. `preloads.py` picks it up automatically, no edit needed.
3. Copy one function + `add_shortcode` pair at the bottom of the snippet, matching the
   key in `data/preloads.json`.
4. Add `hideServerPreload()` to the new tool's render path, copying either existing
   tool. Skipping this leaves the server table stacked above the live one.

## If Code Snippets is ever removed

The shortcodes stop resolving and render as literal bracket text on the page, which is
visible to readers. Remove the shortcodes from the articles, or run
paste the contents of `data/<tool>_preload.html` into a Text Block as raw HTML. The
interactive tools are unaffected either way; they fetch their own data.
