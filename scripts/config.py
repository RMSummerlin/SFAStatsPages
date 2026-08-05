"""
Shared configuration for all SFAStatsPages pull scripts.

One Google Sheet per season. Add a new entry here at the start of each season
(and when backfilling an older season) — no other file needs to change.

Every pull_*.py script must import from here rather than hardcoding a sheet ID,
so a season rollover is a one-line edit that updates every tool at once.
"""

# season -> Google Sheet ID (the long string in the sheet URL between /d/ and /edit)
SEASON_SHEETS = {
    2025: "16um740-9z4_1PUvelr1JHfISOnEqtTQ3bLJl21UoM6s",
    # 2026: "...",   # add at the start of the 2026 season
    # 2024: "...",   # add when backfilling
}

# Tab (gid) within each sheet holding the play-by-play export.
# 0 is the first tab. Override per season here if a sheet is ever laid out differently.
SEASON_GIDS = {}
DEFAULT_GID = 0

# The season the tools open on by default. Always the newest season we have a sheet for,
# so adding a 2026 entry above automatically makes 2026 the default.
CURRENT_SEASON = max(SEASON_SHEETS)

# Backwards-compatible alias for the current season's sheet.
SHEET_ID = SEASON_SHEETS[CURRENT_SEASON]


def csv_url(season: int) -> str:
    """Public CSV export URL for a season's sheet. No API key, no auth."""
    if season not in SEASON_SHEETS:
        raise KeyError(
            f"No sheet configured for season {season}. "
            f"Add it to SEASON_SHEETS in scripts/config.py. "
            f"Known seasons: {sorted(SEASON_SHEETS)}"
        )
    gid = SEASON_GIDS.get(season, DEFAULT_GID)
    return (
        f"https://docs.google.com/spreadsheets/d/{SEASON_SHEETS[season]}"
        f"/export?format=csv&gid={gid}"
    )
