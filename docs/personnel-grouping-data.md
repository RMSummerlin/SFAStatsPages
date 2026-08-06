# Personnel Grouping — data decisions

What `scripts/pull_personnel_grouping.py` does to the raw sheet, and why. Read this
before changing the pull script or debugging a number that looks wrong.

## Which column is the personnel grouping

Not `Formation` (col S) — that column is receiver alignment (`2x2`, `3x1`, `4x1`),
which is a different stat. Personnel comes from **`RBs`, `TEs`, `WRs` (cols BP, BQ, BR)**.

`OffPers` (col O) holds the same thing as a two-digit code, but it is blank on ~2% of
rows (mostly 0-TE and 4-WR sets). Checked against the count columns on 2025 data,
`OffPers == RBs*10 + TEs` on 100% of rows where it is populated, so the script derives
the code from the counts instead and loses nothing.

## Grouping code vs exact personnel

A grouping is **RB-TE only**: `12` is 1 RB and 2 TE. The receiver count is whatever is
left, so it is not part of the code. This matters because of six-OL looks: 1 RB / 2 TE /
1 WR and 1 RB / 2 TE / 2 WR are both 12 personnel, one with an extra offensive lineman.
Splitting them into separate columns would scatter a team's 12-personnel usage across two
places.

So the grid columns fold on RB-TE, and the exact breakdown (including which snaps were
six-OL) shows up in the per-team detail panel. The RB / TE / WR filters always use the
exact counts.

## Dropback vs designed run

`PlayType` alone is not enough:

- Scrambles are coded `RUSH` in the sheet (`Scramble?` = 1), but they are dropbacks.
- Sacks are already coded `PASS`, so they need no special handling.

The script therefore sets `dropback = (PlayType == 'PASS') or Scramble? == 1`, and
everything else is a designed run. The front end exposes just the two choices.

## Field zones

`los` is yards from the opponent's goal line, 1–99 (so `los` = 80 is the offense's own
20). Zones:

| Zone           | `los`  | Meaning                          |
|----------------|--------|----------------------------------|
| Red zone       | 1–20   | inside the opponent's 20         |
| 20 to 50       | 21–50  | opponent's 20 out to midfield    |
| Own territory  | 51–99  | the offense's own side           |

## Score margin

`ScoreDiff` (col CK), verified as `TeamCurrentScore − OppCurrentScore` on every row, so a
negative margin means the offense is trailing. `OppCurrentScore` / `TeamCurrentScore`
(CU, CV) are not needed.

**Neutral game script** = quarters 1–3 and margin within 14 points either way. On 2025
data that is about 66% of all plays.

## What gets excluded

| Reason | 2025 count |
|--------|-----------|
| Kneels and spikes (matched in `PlayDesc`) | 525 |
| Personnel counts missing or not summing to 4 or 5 | 99 |

Kneels and spikes are clock management, not personnel decisions, and they would quietly
inflate heavy-personnel rates for teams that led a lot. A skill-player count of 5 is
standard and 4 is a six-OL look; anything else is incomplete data rather than a real
grouping. Special teams never appear — `PlayType` is only ever `PASS` or `RUSH`.

Every exclusion is counted in the `excluded` object of the output JSON, so the number is
visible rather than silent.

## Efficiency metrics

Three more columns come straight from the sheet, with no derivation:

| Metric | Column | Notes |
|--------|--------|-------|
| EPA per play | `EPA` (CO) | Offense's perspective, so positive is good for the offense |
| Yards per play | `yds` (I) | `Yds` (X) is a byte-identical duplicate; either works |
| Success rate | `SuccessPlay` (CQ) | Already a 0/1 flag, so success is not redefined here |

All three are complete — zero nulls across the plays we keep. `EPA` is always one decimal
place, so it encodes losslessly as `round(EPA * 10)`.

Adding them roughly doubles the payload, from ~50 KB to ~104 KB gzipped. That is the price
of arbitrary client-side filtering on efficiency; there is no aggregation that would help,
for the same reason the play-level format was needed in the first place.

The tool suppresses efficiency below **20 matching plays** and ranks only among offenses
that clear that bar. Eight snaps of 22 personnel can read +0.9 EPA per play, which is
noise presented as insight.

## Output format

One file per season, `data/personnel_grouping_<season>.json`. Every filter is independent
and combinable, so there is no useful pre-aggregation short of the plays themselves —
grouping 2025 by every filter dimension only collapsed 32,703 plays into 30,624 rows.

The file is therefore play-level, stored column-major with one character per play per
field, using a 91-symbol JSON-safe alphabet. Score margin spans two characters
(`mh`, `ml`, base-91, offset by `margin_offset`) so it can never overflow. A full season
is ~320 KB raw and **~50 KB gzipped**, which is what GitHub Pages serves. Decoding is a
`charCodeAt` lookup per field; filtering 33k plays takes a few milliseconds, so every
control responds instantly with no further requests.

`data/personnel_grouping_index.json` lists the published seasons and which one is the
default, so adding a season needs no front-end edit.

## Adding a season

1. Add the sheet to `SEASON_SHEETS` in `scripts/config.py`.
2. `python scripts/pull_personnel_grouping.py --all` to build the new file.
3. Both tools pick it up from the index on their next load. `CURRENT_SEASON` is
   `max(SEASON_SHEETS)`, so the newest season becomes the default automatically.

Past seasons are frozen. The scheduled workflow only re-pulls the current season, so an
archived season's JSON is written once and then left alone.
