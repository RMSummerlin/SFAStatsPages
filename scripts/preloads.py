"""
Collect every tool's crawlable preload table into a single manifest.

Each pull_*.py writes its own `data/<name>_preload.html`. This gathers all of
them into `data/preloads.json`, keyed by tool name:

    {"personnel_grouping": "<table>...</table>", "pace": "<table>...</table>"}

Why bother, when the individual files already exist: the WordPress shortcodes
render the crawlable table server-side, and one manifest means one HTTP request
and one shared cache for every tool, rather than one per tool. Both tables
together are about 2 KB gzipped.

Every pull script calls `write_manifest()` after writing its own table, and the
function rebuilds the whole manifest from whatever is on disk. That makes it
order-independent and idempotent: whichever script runs last leaves a complete
file, and a script that is skipped because its data did not change does not
drop its entry.

Named preloads.py rather than pull_*.py so the scheduled workflow does not try
to execute it, and rather than test_*.py so it is not picked up as a test.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST = DATA_DIR / "preloads.json"
SUFFIX = "_preload.html"


def tool_key(path: Path) -> str:
    """data/personnel_grouping_preload.html -> 'personnel_grouping'"""
    return path.name[: -len(SUFFIX)]


def write_manifest() -> bool:
    """Rebuild data/preloads.json from every *_preload.html on disk.

    Returns True if the file changed, so callers can report it. Writes nothing
    when the content is identical, keeping the "only commit when something
    changed" guarantee intact.
    """
    tables = {}
    for path in sorted(DATA_DIR.glob("*" + SUFFIX)):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            tables[tool_key(path)] = text

    if not tables:
        return False

    payload = json.dumps(tables, separators=(",", ":"), sort_keys=True) + "\n"
    if MANIFEST.exists() and MANIFEST.read_text(encoding="utf-8") == payload:
        return False
    MANIFEST.write_text(payload, encoding="utf-8")
    return True
