# NFL Red Zone Stats

Team red zone efficiency, offense and defense. Two tabs, one table each:
games, trips, trips per game, TD %, scoring %, points per trip, plays per
trip, EPA per play, success rate, pass rate, goal-to-go TD %, inside-10 TD %,
turnovers and TD % over the last four games, with a season pick and a week
range. Every figure carries a rank badge, best first on the side in view
(a low TD % allowed ranks 1 on the defense tab). Any column sorts; the
table opens on TD %, best first. Every team row expands to cards and a
week-by-week chart of trips with touchdowns in red, field goals in grey and
empty trips in light grey. The NFL row pools every trip in view.

There is no explanatory copy inside the tool on purpose: definitions belong
in the article around it. Data decisions are in `docs/redzone-data.md`.

## Files

| File | Role |
|---|---|
| `tool.html` | Working copy with every note. Edit this one. |
| `embed.html` | Same fragment, comments stripped. Paste this one into Avada. Rebuild with `python scripts/build_embed.py`. |

## Data it fetches

Base URL `https://rmsummerlin.github.io/SFAStatsPages/data/`

| File | When |
|---|---|
| `redzone_team_index.json` | on load: which seasons exist, which is the default |
| `redzone_team_<season>.json` | on demand, as a season is picked; per team-week trips, touchdown and field goal trips, points, plays, dropbacks, EPA, successes, turnovers, goal-to-go and inside-10 trips, with the opponent |

Both are written by `scripts/pull_redzone.py`, which also writes the player
page's files. The defense side is not stored: a defense's week is the
offense cell of the team it faced, read through the opponent code.

## What the columns mean

- **Trips**: drives with a pass or rush snap inside the opponent's 20,
  kneel-outs excluded.
- **TD %, Score %**: trips that ended in a touchdown; in a touchdown or a
  field goal.
- **Pts/Trip**: a touchdown is 6 plus the try, a field goal 3, over trips.
- **Plays/Trip, EPA/Play, Succ %, Pass %**: red zone snaps per trip, and
  EPA, success rate and dropback rate on those snaps.
- **G2G TD %, In-10 TD %**: TD rate on trips that had a goal-to-go snap, or
  a snap inside the 10.
- **TO**: turnovers on red zone snaps.
- **Last 4 TD %**: TD % over the team's last four games in range.
- **Rank badge**: under each figure, best first on the side showing. Red for
  the top three. Plays per trip and pass rate have no better side and no
  badge.

## Deep links

`#defense` for the defense tab, `#w3-7` for a week range, `#2025` for a
season, `#kc` to open a team's row; tokens combine with a slash
(`#defense/w2-5/min`). The tool rewrites the hash as the reader changes
things.

## Embedding

Paste the whole of `embed.html` into an Avada custom code block. It is a
fragment: one `<style>`, one `<div class="pt-root pt-rt">`, one `<script>`.
Every selector is scoped `.pt-root.pt-rt`.

Shortcode for the crawlable tables: `[sharp_football_redzone_team]` in a
**Text Block** above the code block (the 32-team offense and defense
tables). The tool hides it once it has painted.

Run `python scripts/lint_embed.py tools/redzone-team/tool.html tools/redzone-team/embed.html`
before pasting.

## Things that will look like bugs but are not

**The box score tool shows a team one or two trips higher.** Its count
includes drives where the only red zone snaps were kneels; this one does not.

**Defense rank 1 is the lowest TD %.** Best first, on the side showing.

**Last 4 TD % equals TD % for the first month.** Four games or fewer played.

**Points per trip reads exactly 7.00 on a one-trip week.** A touchdown that
ended a game is priced from the cached schedule's final score, and assumed
7 if that file is missing.
