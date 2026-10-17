# Red zone pages: talking points

Copy notes for the two articles that wrap the red zone tools, carried over
from the keyword plan (October 2026) and corrected for what the tools
actually do. The keyword decisions, the cannibalization firewall and the
SERP notes stay in that plan; this file is the part an editor needs while
writing. Definitions are in `docs/redzone-data.md`, and every figure the
copy quotes should come from the tool on the day it is written.

Two things the plan said that the build changed:

- **Opportunities, not touches.** Targets plus carries is an opportunity on
  both pages. Not every target is caught, so "touches" overstated it. The
  column is "Opp".
- **Updated after every game, not every Tuesday.** The sheet lands Sunday,
  Monday, Tuesday and Friday and the data refreshes within the hour. The
  Tuesday routine is the weekly H2 rewrite and the FAQ answers, not the
  numbers.

## Page A: NFL Red Zone Targets (player usage)

Slug `/fantasy/nfl-red-zone-targets/`. Shortcode `[sharp_football_redzone]`
in a Text Block above the code block, `tools/redzone/embed.html` in the
code block. Set `TEAM_PAGE` in the embed to Page B's URL.

### First sentence

"NFL red zone targets and carries decide who scores touchdowns, and this
page tracks every player's red zone targets, carries, opportunities and
touchdowns for the season, updated after every game."

### Intro points, 200 to 300 words before the tool

- Why red zone usage is the touchdown stat. The sheet backs Rich's league
  numbers: through week 5 of 2026, 182 of 246 passing touchdowns (74%)
  and 132 of 153 rushing touchdowns (86%) came from inside the 20, and 105
  of the rushing touchdowns from inside the 5. Link the team article for
  the full breakdown.
- Opportunities are not equal: inside the 10 and inside the 5 are where the
  TD rate jumps, which is why the toggle exists. Quote the league TD rate
  per opportunity at each zone from the footer of the three Leaders boards.
- Share beats count: ten red zone targets on a team with 60 red zone plays
  is a different player from ten on a team with 30. Name the Tgt % and
  Car % columns and the opportunity share in the detail card.
- The three tabs in one sentence each. The Updated line with the week.
- Scope: regular season, offensive snaps inside the opponent's 20, kneels
  and spikes excluded, two-point tries not in the data, plays wiped out by
  penalty dropped.

### H2 outline

1. **How to Read the Red Zone Targets and Carries Table.** One line per
   column, in the order the table shows them. The zone toggle. Why a very
   high TD rate on few opportunities regresses. The minimum-opportunities
   filter and the show-all button.
2. **NFL Red Zone Report: Week N Targets, Carries and Touchdowns.** The
   rotating block. Five to eight bullets with numbers: the week's most red
   zone targets and carries (Leaders tab, with only that week picked), the
   biggest share changes, players with high usage and no touchdowns (buy),
   players with touchdowns on low usage (sell). Rewritten every Tuesday,
   no archive.
3. **Red Zone Carries and Goal Line Touches: Running Backs and
   Quarterbacks.** Carries inside the 5 as the touchdown-equity stat; the
   goal line back against the lead back; teams where the quarterback's
   designed runs inside the 5 cap the back. Scrambles count as carries, so
   say so. Link `#zone5/rb` and `#zone5/qb`.
4. **Red Zone Targets by Position: Wide Receivers and Tight Ends.** Tight
   end red zone targets as the position's whole case; a receiver's red zone
   target share against his overall target share (snap counts tool for the
   latter); the end zone target as the highest-value look. Link `#te` and
   `#zone10/wr`.
5. **Red Zone Targets and Carries by Team.** How each offense spreads its
   red zone work; the Teams tab's header line (plays, pass rate, share of
   plays that scored) and the link to Page B for trips and points per trip.
   Carry the team tail in body text with `#teams/lac`-style links; one
   sentence per team is enough.
6. **Using Red Zone Usage for Fantasy Football and Betting.** Fantasy: high
   usage and low touchdowns as the buy, touchdowns on low usage as the sell;
   pair with snap share, expected fantasy points and the matchup (the DvP
   page's Red Zone filter). Betting: anytime touchdown props follow carries
   inside the 5 and targets inside the 10; link the player prop odds hub.
   No picks.
7. **Red Zone Targets FAQ** (FAQPage schema once the copy is live).
   - What counts as a red zone target or carry? Inside the opponent's 20;
     a sack or throwaway is not a target; a scramble is a carry.
   - Who has the most red zone targets this season? The most red zone
     carries? Weekly answers with numbers from the Leaders tab.
   - What is a good red zone target share? Quote the top of the Tgt %
     column for players with 10 or more opportunities.
   - Why do red zone touchdowns regress? Two sentences; link Rich's
     articles as the long read.
   - Is this the same as the NFL RedZone channel? No; one sentence. Never
     write "redzone" as one word in a heading.
   - How often is it updated? After every game. How far back? 2021.

## Page B: NFL Red Zone Stats (team offense and defense)

Slug `/stats-nfl/nfl-red-zone-stats/` once the redirect to the QB article
is cleared, otherwise `/stats-nfl/nfl-red-zone-efficiency/`. Shortcode
`[sharp_football_redzone_team]`, embed `tools/redzone-team/embed.html`.
No Trends tab was built; the season-over-season view stays in prose.

### First sentence

"NFL red zone stats for all 32 offenses and defenses: trips, touchdown rate,
scoring rate, points per trip and the efficiency behind them, updated after
every game."

### H2 outline

1. **How to Read the Red Zone Stats Table.** Trips against efficiency; why
   points per trip beats TD %; the rank badge under every figure; the NFL
   row pools every trip rather than averaging 32 rates.
2. **Best and Worst NFL Red Zone Offenses This Season.** Weekly: top three
   and bottom three by TD % and points per trip with the numbers.
3. **NFL Red Zone Defense Rankings.** Weekly top and bottom three allowed;
   the bend-but-don't-break profile (high yards allowed, low red zone TD %).
   Link `#defense`.
4. **Red Zone Trips vs. Red Zone Efficiency.** A team can rank first in
   trips and 25th in TD %; the Trips and Trips/G columns next to TD %; link
   the offensive stats page for drive stats.
5. **Red Zone Touchdown Percentage This Season vs. Last Season.** Prose,
   from the season pick; link Rich's team article as the offseason read.
   Keep "regression" out of the heading.
6. **Using Red Zone Stats for Betting and Fantasy.** Totals and team totals
   context (odds hub, implied totals); fantasy touchdown environment (Page
   A, the Worksheet hub). No picks.
7. **NFL Red Zone Stats FAQ.** What counts as a red zone trip (a drive with
   a pass or rush snap inside the 20, kneel-outs excluded); what is a good
   red zone TD % (quote the league row); which team has the best red zone
   offense and defense this season (weekly); how often it updates.
