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
    2024: "1s_LyoK6k2EgAOZFXmDCq5u3WNzZPQJNjfmbHENX8vUo",
    2023: "1sa3x3IfkiAQzAaHw4swU9kgImZ9-_h543ocHMTP1DOE",
    2022: "1LXxpvBHbgmFxxDpFMvtJC40MVzg2EpwQNGdSIZhkgKc",
    2021: "17D8yT9Gh8WG4ijxBlWjPjWgp6ZqzgmLj0OjzTp0Dfk4",
    # 2026: "...",   # add at the start of the 2026 season
}

# Tab (gid) within each sheet holding the play-by-play export.
# 0 is the first tab. Override per season here if a sheet is ever laid out differently.
#
# The 2021-2024 sheets were copied from a common template, so the play-by-play tab
# kept its id and is NOT the first tab. Without these overrides the pull would
# silently read whatever sits on tab 0. Check the gid= in a new sheet's URL before
# assuming it is 0.
SEASON_GIDS = {
    2024: 1392276586,
    2023: 1392276586,
    2022: 1392276586,
    2021: 1392276586,
}
DEFAULT_GID = 0

# The season the tools open on by default. Always the newest season we have a sheet for,
# so adding a 2026 entry above automatically makes 2026 the default.
CURRENT_SEASON = max(SEASON_SHEETS)

# Backwards-compatible alias for the current season's sheet.
SHEET_ID = SEASON_SHEETS[CURRENT_SEASON]



# Franchises pooled under one code so a multi-season view shows 32 rows rather
# than one row per name a franchise has worn. Without this, selecting 2021 next
# to 2025 lists WFT and WAS as if they were different teams — which is exactly
# what the tool did before this map existed.
#
# Two groups, both mapping to whatever the franchise is called now:
#   * relocations and renames — WFT/WSH, OAK, SD, STL
#   * alternate abbreviations for the same team, which differ between data
#     providers and have a habit of changing when a sheet is rebuilt
#
# Rule of thumb for additions: normalise toward the CURRENT code, so history
# folds into the present rather than the present being renamed into history.
TEAM_ALIASES = {
    # Washington: Redskins -> Football Team (2020-21) -> Commanders
    "WFT": "WAS", "WSH": "WAS", "WAS": "WAS",
    # Oakland -> Las Vegas, 2020
    "OAK": "LV", "LVR": "LV", "RAI": "LV",
    # San Diego -> Los Angeles, 2017
    "SD": "LAC", "SDG": "LAC",
    # St. Louis -> Los Angeles, 2016. "LA" is ambiguous in principle, but every
    # feed that uses it means the Rams; the Chargers have always been LAC here.
    "STL": "LAR", "SL": "LAR", "LA": "LAR", "RAM": "LAR",
    # Same franchise, different house style
    "JAC": "JAX", "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
    "TAM": "TB", "KAN": "KC", "NOR": "NO", "SFO": "SF", "GNB": "GB",
    "NWE": "NE", "NORL": "NO", "TBB": "TB",
}


def canonical_team(code):
    """Fold a team abbreviation onto the franchise's current code."""
    code = (code or "").strip().upper()
    return TEAM_ALIASES.get(code, code)


# Read-only scopes for the service account. Drive is needed as well as Sheets
# because the CSV export endpoint is served by Drive.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


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
