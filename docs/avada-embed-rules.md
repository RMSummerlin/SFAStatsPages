# Avada Embed Rules

Ground rules for any HTML/CSS/JS tool built in this repo that will be pasted into a custom code container on the Sharp Football Analysis Avada (WordPress) site. Every tool must follow these to avoid clashing with the theme.

## Audience: mobile-first

~75% of traffic is mobile. Design and build **narrow-first**, then enhance for larger screens.

- Default styles target mobile. Add `min-width: 641px` media queries to enhance for desktop — never the reverse.
- Tap targets: minimum 44x44px.
- Navigation: thumb-friendly, no reliance on hover states.
- Dense data (tables, stat grids): needs a mobile-specific treatment — cards, expandable rows, or horizontal scroll with fixed key column. Never ship a desktop table that just shrinks.
- Raise mobile UX concerns proactively before building, not after.

## Delivery format

Every tool must be a **fragment**, not a full document, because it's pasted directly into an Avada custom code block on an existing page:

- One `<style>` block
- One root `<div class="pt-root">...</div>`
- One `<script>` block
- **Never** include `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, `<meta>`, or `<title>` — the page already has these.

## Two files: tool.html and embed.html

The fragment lives in the repo twice.

| File | Role |
|---|---|
| `tools/<name>/tool.html` | The working copy. Carries every note explaining why the code is the way it is. Edit this one. |
| `tools/<name>/embed.html` | The same fragment with all comments removed. **Paste this one into Avada.** |

The published page's source is readable by anyone, so notes about which Avada rule a
workaround exists for, or why a median beat a mean, do not belong in what ships.

`embed.html` is generated, never hand-written:

```
python scripts/build_embed.py           # rebuild every tool's embed.html
python scripts/build_embed.py --check   # fail if any is stale, write nothing
```

It deletes comments and changes nothing else — no minifying, no renaming, no reordering —
so the two files diff cleanly and a bug in one reproduces in the other. It parses the
fragment rather than pattern-matching, because `//` also appears in the GitHub Pages URL
and `/*` can appear inside a string or a regex literal, and it refuses to write if the
script no longer parses, if any non-comment character moved, or if a URL or string
literal changed.

## CSS scoping

- Every selector must be scoped under `.pt-root`. Never write bare `*`, `body`, `header`, `input`, `button`, etc. — these leak into and clash with the Avada theme.
- The universal reset must be written as `.pt-root *{}`, not `*{}`.
- Add `font-family: inherit;` to form controls so they pick up the brand font instead of browser defaults.

## No semantic landmark elements

Do not use `<header>`, `<footer>`, `<nav>`, `<main>`, or `<section>` — Avada hooks theme CSS/JS onto these tags, causing style bleed and JS conflicts. Use prefixed divs instead: `.pt-header`, `.pt-footer`, `.pt-nav`, etc.

## Positioning

- **No `position: fixed`** for in-flow UI — it escapes the container and overlaps the site header/footer.
- `position: fixed` is only acceptable for an intentional full-screen modal.
- Plain `position: sticky` is fine for short tools, but see below for long lists.

## Height: full view, one scrollbar

A tool shows at its full height and the page scrolls. The root carries **no `max-height`
and no `overflow`**, so the site has one scrollbar rather than one inside the tool and
one outside it. The tools used to be bounded panels (`max-height: 85svh` on a phone, a
`clamp()` on a desktop) with an internal scrollbar; that was dropped in October 2026
because the nested scroll performed badly, and `scripts/lint_embed.py` now warns if a
root is capped.

What follows from that:

- **Wide tables pan sideways, nothing scrolls vertically inside the tool.** The body
  wrapper is `overflow-x: auto` only, so the rank and team columns can stay `sticky`
  on the left while a phone pans across the figure columns.
- **No vertical `sticky` on column heads or footers.** With the page doing the
  scrolling they would pin to the viewport, under the site's fixed header. Leave them
  in flow.
- **A modal sheet is `position: fixed`**, anchored to the viewport and capped at
  `84svh`, with its scrim fixed too. This is the one use of `position: fixed` the rules
  allow. Anchored to the root instead, it would sit at the bottom of a tool that is as
  tall as its content, well below the control that opened it. See the game picker in
  the matchup and box score tools.
- **No height cap from the script either.** The `capHeight()` routine that used to fix
  the phone cap in pixels (because some browsers let `svh` track the URL bar) is gone
  with the cap.

One thing the live site taught, already in every tool and worth copying into a new one:

- **Pin every edge a table draws.** On the phone layout the theme drew a box round every cell of the last figure column, and the class-scoped reset at the top of the fragment loses to a theme rule written with `!important`. Each table declares its own borders with `!important` under a `.pt-root.pt-xx[data-init] .pt-grid tr>td` selector (`data-init` is the attribute the script sets on the root, used only to outrank theme rules that have no id), sets `border-top`, `border-left`, `border-right`, `outline` and `box-shadow` to nothing, and re-asserts the few edges it wants (header rule, team divider, footer rule).

## Brand font

Interstate Condensed, self-hosted at:
`https://www.sharpfootballanalysis.com/wp-content/themes/Avada-child/fonts/`

```css
.pt-root {
  font-family: 'Interstate Condensed', sans-serif;
}
.pt-root input, .pt-root select, .pt-root button, .pt-root textarea {
  font-family: inherit;
}
```

## Brand colors

| Use            | Color                  |
|-----------------|------------------------|
| Black            | `#000`                 |
| Header band      | `#222529` — the masthead and sheet headers; matches the site header, and pure black next to the red rule vibrates |
| Sharp red        | `#cc0000`               |
| Background       | `#f4f5f7` / `#fff` / `#f9fafb` |
| Table stripe     | `#f6f6f6` — every other row of a two-column comparison table |
| Text             | `#111`                  |
| Muted text       | `#4e5154` — captions, labels, footers, the "other" figure in a comparison. 8.6:1 on white |
| Gray (secondary) | `#7f8c9a` — figures 24px and up (a losing score), shapes, swatch borders, control edges. **Not for text under 24px**: it is 3.4:1 on white and fails |
| Gray (tertiary)  | `#b0bec5` — shapes and dividers only |
| Border           | `#cdd5de` / `#dde2e8` — dividers and table rules. A control edge (a select, a picker, a filter button, a toggle) uses `#7f8c9a` instead: an edge needs 3:1 against its surface and these are 1.3:1 |

## Type and contrast

These came out of the box score visual rework (September 2026) and apply to every tool.
`scripts/lint_embed.py` fails a fragment that breaks the floor.

- **Nothing under 11px**, in CSS or in the font sizes a script writes into an SVG chart.
  Three quarters of the traffic is on a phone; 8px picker keys and 9px column heads with
  wide tracking are not readable there. Section heads, column heads, season figures and
  chart captions are 11px; footers, legends and notes 12px.
- **Text must clear 4.5:1** on the darkest surface it can sit on (`#f4f5f7`). That rules
  out `#7f8c9a` under 24px and every raw team colour on a figure — see the team palette.
- **Figures are the product.** In a table they are never smaller than their labels: 15px
  figures against 14px labels. The better side of a comparison is bold ink; the other side
  is regular weight in muted grey, so weight carries the answer rather than two coloured
  numbers shouting at each other.
- **A comparison table is striped** (`#f6f6f6`) and its rows are 44px tall, which is also
  the touch floor.
- **Red is the brand signal**, spent on the masthead rule and the week badge. Date lines,
  kickoff times and other secondary copy are sentence case in muted grey, not red caps.
- **Say a thing once.** A diverging bar with both figures at its ends does not also need a
  caption stating the gap, or tick marks on a scale that is never labelled.

### Team colours

Tools that paint teams share one palette (the `COLORS` map in the box score and matchup
fragments), three values per team:

| Value | Paints | Why |
|---|---|---|
| fill | Large shapes only: the 5px rule over a team name, a bar, a swatch | The real brand colour. Carries no text, so it needs no contrast floor and Packers gold stays gold |
| text | Letters and figures | The brand colour darkened in-hue until it clears 4.5:1 on `#f4f5f7`. The only team colour allowed on type |
| fallback | Both, when the two teams in a game clash | The team's other brand colour, already text-safe |

Two teams clash when either their text colours or their fill colours land within a CIE76
ΔE of 22. The home team then tries its fallback, then its text colour as the fill too, and
only if neither separates them does the away team change; every ordered pairing in the
league resolves this way. Colour is still never the only thing telling the two sides
apart: rows carry the abbreviation at both ends and keep away left, home right.

## Data fetching

Tools pull live data from this repo's GitHub Pages endpoint (static JSON generated by the Python pipeline — see main README), e.g.:

```js
fetch('https://<username>.github.io/SFAStatsPages/data/example.json')
```

No API keys or secrets should ever appear in embed code — all data is public and pre-processed before publishing.

## Pre-ship checklist

- [ ] Fragment only — no doc-level tags
- [ ] All CSS scoped under `.pt-root`
- [ ] No semantic landmark elements
- [ ] No `position: fixed` outside of intentional modals
- [ ] No `max-height` or `overflow` on the root; the page scrolls, wide tables pan sideways
- [ ] Brand font + colors applied
- [ ] Nothing under 11px; text under 24px is `#111` or `#4e5154`, never `#7f8c9a`; control edges are `#7f8c9a`
- [ ] Mobile layout designed first, verified at narrow width before desktop enhancement
- [ ] Tap targets ≥44x44px
- [ ] `python scripts/build_embed.py` run, so `embed.html` matches `tool.html`
- [ ] The code pasted into Avada came from `embed.html` — no development notes in the published page source
- [ ] Tested inside an actual Avada custom code block, not just standalone
