#!/usr/bin/env python3
"""
Drop the freshly generated static tables into each tool fragment, between the
SFA:PRELOAD markers.

Run this locally after pull_personnel_grouping.py, then copy the updated
tool.html into its Avada custom code block. That static table is what search
engines read, so refreshing it every week or two during the season keeps the
crawlable snapshot close to live. The interactive tool is always live either way.

On a page that also carries the WordPress shortcode, the same table would appear
twice in the raw HTML. Use --strip to empty the markers instead of filling them,
leaving the shortcode as the only crawlable copy:

  python scripts/refresh_preload.py --strip

Only do that for tools whose article actually carries the shortcode. Without it,
--strip leaves no crawlable table at all.

Named refresh_* rather than pull_* so the scheduled workflow ignores it — the
workflow only commits data/, so patching tools/ belongs in a manual step.

  python scripts/refresh_preload.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
START = "<!-- SFA:PRELOAD:START -->"
END = "<!-- SFA:PRELOAD:END -->"

# tool folder -> generated snippet in data/
PAIRS = {
    "personnel-grouping": "personnel_grouping_preload.html",
    "pace": "pace_preload.html",
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    strip = "--strip" in argv
    changed = 0
    for folder, snippet in PAIRS.items():
        tool = REPO_ROOT / "tools" / folder / "tool.html"
        src_file = REPO_ROOT / "data" / snippet
        if not tool.exists():
            print(f"skip  {folder} — no tool.html yet")
            continue
        if not src_file.exists() and not strip:
            print(f"skip  {folder} — {snippet} not generated yet; "
                  f"run pull_personnel_grouping.py first")
            continue

        html = tool.read_text(encoding="utf-8")
        if START not in html or END not in html:
            print(f"FAIL  {folder} — preload markers missing from tool.html")
            return 1

        table = "" if strip else src_file.read_text(encoding="utf-8").strip()
        head, rest = html.split(START, 1)
        _, tail = rest.split(END, 1)
        new = head + START + "\n" + table + "\n" + END + tail
        if new != html:
            tool.write_text(new, encoding="utf-8")
            changed += 1
            what = "stripped" if strip else f"refreshed ({len(table):,} chars)"
            print(f"ok    {folder} — preload table {what}")
        else:
            print(f"ok    {folder} — already current")
    print(f"\n{changed} file(s) updated. Re-paste any updated tool.html into Avada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
