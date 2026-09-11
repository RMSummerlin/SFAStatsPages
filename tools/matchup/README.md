# Weekly Matchups

One game at a time: how each offense ranks against the defense it faces in five
battles (overall efficiency, passing, rushing, pressure, explosive plays), with
the gap between the two drawn as an edge. Week stepper, a game picker that
doubles as the slate view, and a tap-to-open detail sheet with the numbers
behind every rank.

Data decisions, the blend, and the backtest that set its parameters are in
`docs/matchup-data.md`. Read that before changing anything numeric.

## Files

| File | Role |
|---|---|
| `tool.html` | Working copy with every note. Edit this one. |
| `embed.html` | Same fragment, comments stripped. Paste this one into Avada. Rebuild with `python scripts/build_embed.py`. |

## Data it fetches

Base URL `https://rmsummerlin.github.io/SFAStatsPages/data/`

| File | When |
|---|---|
| `matchup_index.json` | on load: which seasons exist, which is default |
| `matchup_<season>.json` | on load: schedule, results, the latest as-of snapshot in full, every earlier snapshot's battle scores, trend series |
| `matchup_<season>_w<W>.json` | on demand, when a battle row is tapped on a card for an earlier week |

All written by `scripts/pull_matchup.py`, which also needs the nflverse schedule
and `data/offseason_changes_<season>.json` (see the docs).

## Embed notes

* Root is `.pt-root.pt-mu`; every selector is scoped to the pair.
* Shortcode for the crawlable table: `[sharp_football_matchup]` in a **Text
  Block** above the code block. `[sharp_football_matchup game="KC-BUF"]` (away
  team first) keeps just that game's two rows for a preview article.
* Deep links: `#w3-kc-buf` opens week 3, KC at BUF. The tool rewrites the hash
  as the reader navigates, with `replaceState`, so it never adds history entries.
* The bottom sheet is `position:absolute` inside the root and scrolls
  internally. No `position:fixed`.
* On a phone one side of the ball shows at a time behind a toggle; at 641px and
  up both panels sit side by side and the toggle is hidden.

## Things that look like bugs but are not

* **Every fill is hatched and faded before week 1.** That is the design: the
  rating is entirely last season's regressed baseline, and the hatch says so.
  Fills solidify as this season's share grows.
* **Defensive ranks bunch and most defensive rows read "Even" early.** Defense
  is far less predictable than offense (see the backtest), so its prior is
  regressed to 0.2 of last season's deviation. Ranks spread out as games land.
* **The card for a future week looks identical to this week's.** No games have
  been played between them, so it reads the latest snapshot. The basis line
  says so.
* **Stepping back to an old week changes nothing on later weeks.** Snapshots
  are as-of and frozen; that is the point of the stepper.
* **A team is flagged "New QB" when its week 1 starter was always the plan.**
  The changes file compares against last season's most common starter, so a
  rookie or free-agent signing is new by that definition. Correct the file by
  hand if the flag is wrong.
* **"New since wk N" appears mid-season without any file edit.** The schedule's
  listed starter differs from the one who opened the season; the offense prior
  gets the QB haircut from that week on.
* **A split shows a dash but still carries a rank.** The dash is the 40-play
  gate this season; the rank is on the blended value, which exists.
* **The mismatch sort puts a game with no huge single edge near the top.** It
  sums ten absolute edges, so five moderate edges outrank one big one.
* **The final score appears on a card but the offense EPA line does not.**
  nflverse has the score; the sheet does not have the game yet.
* **Percentiles, not raw values, drive the bar length.** A 1st vs 32nd pairing
  fills the half-track regardless of how far apart the underlying numbers are.
  The pop-out dumbbells show the actual distance.
