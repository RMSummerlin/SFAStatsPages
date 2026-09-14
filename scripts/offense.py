"""
Fold a sheet that logs every play twice — once per team — down to the offense's row.

The 2026 sheet arrived in a new shape: every play appears on two rows, one from
each team's point of view, with `team` and `opponent` swapped and the
perspective columns (HomeRoad, ScoreDiff, the score and timeout columns)
flipped. Nothing on either row says which of the two is the offense, and the
2021-2025 sheets carried one row per play with `team` meaning the offense. Left
alone, every pull script credited each team with its opponent's snaps as well
as its own: 120 plays a game, 26 drives, a pass rate that was the average of two
offenses. This module gives the pull scripts back the shape they were written
for.

Which copy is the offense is inferred from three things, in order of trust:

1. Player identity. Passer, rusher and target IDs belong to one team, so any
   two drives in a game that share a player were run by the same offense. A
   union-find over drives splits a game into (almost always exactly) two
   clusters. This is the strong signal: it decides *grouping* for every drive
   that shares a player with any other.
2. The yard line in the play description. NFL gamebook text ends a play at a
   spot like `to HST 36`, and `los` (yards to the opponent's goal line before
   the snap) minus `yds` says where that spot is. If the spot's number equals
   100 minus that distance the ball is on the offense's own side, so the side
   code IS the offense; if it equals the distance the ball is on the defense's
   side. Both equalities are checked exactly, and turnover, penalty and no-play
   descriptions are skipped, because on those the spot marks where the ball
   changed hands rather than where the play ended. Votes are summed per
   cluster, so a cluster of a dozen drives carries dozens of votes and one odd
   description cannot flip it.
3. Alternation. A drive whose players appear nowhere else and whose plays
   carry no usable spot (a lone spike, an incomplete pass into halftime) takes
   the opposite offense of its nearest decided neighbour, by drive-number
   parity. Possession alternates on every change of drive except the odd
   onside kick, so this is right in practice and only ever reaches a play or
   two a week.

A game where none of that decides anything is a parse failure, not data, and
raises rather than publishing.

Rows that are not mirrored pass through untouched, so the 2021-2025 sheets and
every test fixture are unaffected. The flag columns the provider fills on only
one of the two copies (pressure, blitz, hit, penalty first downs) are merged
onto the kept row so the matchup splits that read them keep working.

A one-row-per-play sheet still gets the yard-line check, as a guard: the
provider's export has no offense marker, so a sheet pasted from the wrong
side would credit every play to the defense and nothing downstream would
notice. If more than a fifth of the plays that can be checked say the row's
team is the defense, the pull stops rather than publishing.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

import config

# Filled from the row team's point of view, so they must come from the offense's
# copy and never be merged across from the other one.
PERSPECTIVE_COLUMNS = {
    "team", "opponent", "HomeRoad", "ScoreDiff", "TeamCurrentScore",
    "OppCurrentScore", "DriveTOUsed", "DriveOppTOUsed", "DriveStartTOLeft",
    "DriveStartOppTOLeft",
}

PLAYER_ID_COLUMNS = ("PasserID", "RusherID", "TargetID")
PLAYER_NAME_COLUMNS = ("PasserName", "RusherName", "TargetName")

# "to HST 36", "pushed ob at BUF 46". Never "to 50" (no side at midfield) and
# never "to 4-J.Cook" (a jersey number, not a team code).
SPOT_RE = re.compile(r"\b(?:to|at)\s+([A-Z]{2,3})\s+(\d{1,2})\b")
# Descriptions whose spot marks something other than where the play ended.
NO_VOTE_RE = re.compile(r"intercept|fumble|penalty|no play|reversed|touchdown",
                        re.IGNORECASE)

# What counts as "not filled in" when merging a flag from the discarded copy.
EMPTY = {"", "0", "0.0"}

# The one-row-per-play guard needs this many checkable plays before it judges,
# and stops the pull if more than this share of them say team is the defense.
MIN_CHECK_VOTES = 20
MAX_DISAGREE = 0.2


def _s(row, col):
    return (row.get(col) or "").strip()


def _num(value):
    try:
        return float(value.strip())
    except (AttributeError, ValueError):
        return None


def mirrored_pairs(rows):
    """Index pairs of rows that are the same play seen from both teams.

    Returns {(GameId, PlayId): [i, j]} for every play logged exactly twice with
    team and opponent swapped. Empty when the sheet is one row per play.
    """
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        gid, pid = _s(row, "GameId"), _s(row, "PlayId")
        if gid and pid:
            groups[(gid, pid)].append(i)
    pairs = {}
    for key, ix in groups.items():
        if len(ix) != 2:
            continue
        a, b = rows[ix[0]], rows[ix[1]]
        ta, oa = config.canonical_team(a.get("team")), config.canonical_team(a.get("opponent"))
        tb, ob = config.canonical_team(b.get("team")), config.canonical_team(b.get("opponent"))
        if ta and oa and ta != oa and ta == ob and oa == tb:
            pairs[key] = ix
    return pairs


def spot_vote(row, home, away):
    """Which team the play description says had the ball, or None."""
    desc = row.get("PlayDesc") or ""
    if NO_VOTE_RE.search(desc):
        return None
    m = SPOT_RE.search(desc)
    los, yds = _num(row.get("los")), _num(row.get("yds") or row.get("Yds"))
    if not m or los is None or yds is None:
        return None
    side = config.canonical_team(m.group(1))
    spot = int(m.group(2))
    end = los - yds                      # yards to the opponent's goal after the play
    if side not in (home, away) or end == 50:
        return None
    if spot == 100 - end:                # ball on the offense's own side of the field
        return side
    if spot == end:                      # ball on the defense's side
        return away if side == home else home
    return None


def _decide_game(plays, home, away):
    """plays: list of (key, row) for one game, one copy per play.

    Returns ({key: offense_team}, Counter of how drives were decided).
    """
    fields = plays[0][1].keys()
    id_cols = [c for c in PLAYER_ID_COLUMNS if c in fields] or \
              [c for c in PLAYER_NAME_COLUMNS if c in fields]

    drives = defaultdict(list)           # drive label -> [(key, row)]
    for key, row in plays:
        d = _num(row.get("DriveNumber"))
        drives[int(d) if d is not None else ("play", key)].append((key, row))

    # 1. Cluster drives that share a player.
    parent = {d: d for d in drives}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for d, items in drives.items():
        for _, row in items:
            for col in id_cols:
                pid = _s(row, col)
                if not pid:
                    continue
                if pid in owner:
                    parent[find(d)] = find(owner[pid])
                else:
                    owner[pid] = d

    # 2. Name each cluster by the yard-line votes of all its plays.
    votes = defaultdict(Counter)
    for d, items in drives.items():
        for _, row in items:
            v = spot_vote(row, home, away)
            if v:
                votes[find(d)][v] += 1
    offense = {}
    how = Counter()
    for d in drives:
        tally = votes[find(d)]
        if tally[home] != tally[away]:
            offense[d] = home if tally[home] > tally[away] else away
            how["by players and description"] += 1

    # 3. Anything left alternates from its nearest decided drive.
    decided = sorted(d for d in offense if isinstance(d, int))
    for d in drives:
        if d in offense:
            continue
        if not isinstance(d, int) or not decided:
            continue
        nearest = min(decided, key=lambda e: (abs(d - e), e))
        same = (d - nearest) % 2 == 0
        offense[d] = offense[nearest] if same else (away if offense[nearest] == home else home)
        how["by alternation"] += 1

    out = {}
    for d, items in drives.items():
        if d not in offense:
            return None, how
        for key, _ in items:
            out[key] = offense[d]
    return out, how


def offense_check(rows):
    """Guard a one-row-per-play sheet: does `team` look like the offense?

    Returns a note for the log, or None when too few plays can be checked (a
    sheet without play descriptions, or a test fixture). Raises SystemExit when
    the descriptions say the rows are the defense's copy.
    """
    agree = disagree = 0
    for row in rows:
        team = config.canonical_team(row.get("team"))
        opp = config.canonical_team(row.get("opponent"))
        if not team or not opp or team == opp:
            continue
        vote = spot_vote(row, team, opp)
        if vote == team:
            agree += 1
        elif vote == opp:
            disagree += 1
    total = agree + disagree
    if total < MIN_CHECK_VOTES:
        return None
    if disagree > MAX_DISAGREE * total:
        raise SystemExit(
            f"The sheet has one row per play, but on {disagree:,} of {total:,} plays "
            f"that could be checked the yard line in PlayDesc says `team` is the "
            f"DEFENSE, not the offense. It looks like the defensive copy of the "
            f"export was pasted in. Re-paste the offensive rows (or both copies, "
            f"which are folded automatically) and re-run.")
    return (f"one row per play; yard-line check agrees team is the offense on "
            f"{agree:,} of {total:,} checkable plays.")


def offense_rows(rows):
    """Keep one row per play — the offense's — when the sheet logs each play twice.

    Returns (rows, note). When the sheet is not mirrored, rows is the input
    object unchanged and note is the guard's verdict (None if it could not
    judge). Otherwise a new list in the original order and a one-line
    description for the log.
    """
    pairs = mirrored_pairs(rows)
    if not pairs:
        return rows, offense_check(rows)

    by_game = defaultdict(list)
    for key, (i, j) in pairs.items():
        a, b = rows[i], rows[j]
        # Read every game from the home team's side; either side works, this
        # just makes the logs consistent.
        first = a if _s(a, "HomeRoad").lower().startswith("h") or not _s(b, "HomeRoad").lower().startswith("h") else b
        by_game[key[0]].append((key, first))

    keep = set()
    how = Counter()
    failed = []
    for gid, plays in by_game.items():
        home = config.canonical_team(plays[0][1].get("team"))
        away = config.canonical_team(plays[0][1].get("opponent"))
        decided, game_how = _decide_game(plays, home, away)
        if decided is None:
            failed.append(gid)
            continue
        how.update(game_how)
        for key, _ in plays:
            i, j = pairs[key]
            off, other = (i, j) if config.canonical_team(rows[i].get("team")) == decided[key] else (j, i)
            keep.add(off)
            kept, dropped = rows[off], rows[other]
            for col in kept:
                if col in PERSPECTIVE_COLUMNS:
                    continue
                if _s(kept, col) in EMPTY and _s(dropped, col) not in EMPTY:
                    kept[col] = dropped[col]

    if failed:
        raise SystemExit(
            "Could not tell offense from defense in game(s) "
            + ", ".join(sorted(failed))
            + ": no drive had a usable yard line in its play descriptions. "
            "Check the PlayDesc, los and yds columns.")

    paired = {i for ix in pairs.values() for i in ix}
    out = [row for i, row in enumerate(rows) if i in keep or i not in paired]
    unpaired = len(rows) - len(paired)
    note = (f"sheet logs each play once per team; kept the offense's copy "
            f"({len(keep):,} of {len(rows):,} rows"
            + (f", {unpaired:,} unpaired rows passed through" if unpaired else "")
            + "). Drives decided "
            + ", ".join(f"{n:,} {label}" for label, n in sorted(how.items())) + ".")
    return out, note
