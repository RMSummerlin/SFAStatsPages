#!/usr/bin/env python3
"""
Check a tool fragment against docs/avada-embed-rules.md before it goes into an
Avada custom code block.

  python scripts/lint_embed.py                      # every tools/*/tool.html
  python scripts/lint_embed.py tools/x/tool.html    # one file

Named lint_* rather than pull_* so the scheduled workflow ignores it.
Exits non-zero if anything fails, so it can gate a commit.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_LEVEL_TAGS = ["<!doctype", "<html", "<head", "<body", "<meta", "<title"]
LANDMARKS = ["header", "footer", "nav", "main", "section", "article", "aside"]
BRAND_COLORS = {"#cc0000", "#000", "#111", "#7f8c9a", "#b0bec5",
                "#cdd5de", "#dde2e8", "#f4f5f7", "#f9fafb", "#fff"}


def selectors(css):
    """Yield every selector in a stylesheet, flattening @media blocks."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    out = []
    i = 0
    while i < len(css):
        brace = css.find("{", i)
        if brace == -1:
            break
        head = css[i:brace].strip()
        if head.startswith("@"):
            if head.split()[0] in ("@media", "@supports"):
                depth, j = 1, brace + 1
                while depth and j < len(css):
                    if css[j] == "{":
                        depth += 1
                    elif css[j] == "}":
                        depth -= 1
                    j += 1
                out.extend(selectors(css[brace + 1:j - 1]))
                i = j
                continue
            depth, j = 1, brace + 1
            while depth and j < len(css):
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            i = j
            continue
        close = css.find("}", brace)
        if close == -1:
            break
        for sel in head.split(","):
            sel = sel.strip()
            if sel:
                out.append(sel)
        i = close + 1
    return out


def lint(path: Path):
    src = path.read_text(encoding="utf-8")
    low = src.lower()
    fails, warns = [], []

    for tag in DOC_LEVEL_TAGS:
        if tag in low:
            fails.append(f"contains document-level tag {tag!r} — fragments must not")

    for tag in LANDMARKS:
        if re.search(r"<" + tag + r"[\s>]", low):
            fails.append(f"uses <{tag}> — Avada hooks theme CSS/JS onto it; "
                         f"use a .pt-{tag} div instead")

    styles = re.findall(r"<style>(.*?)</style>", src, re.S)
    scripts = re.findall(r"<script>(.*?)</script>", src, re.S)
    if len(styles) != 1:
        fails.append(f"expected exactly one <style> block, found {len(styles)}")
    if len(scripts) != 1:
        fails.append(f"expected exactly one <script> block, found {len(scripts)}")

    roots = re.findall(r'<div class="pt-root([^"]*)"', src)
    if len(roots) != 1:
        fails.append(f"expected exactly one .pt-root element, found {len(roots)}")

    if styles:
        css = styles[0]
        for sel in selectors(css):
            if not sel.startswith(".pt-root"):
                fails.append(f"unscoped selector {sel!r} — must start with .pt-root")
        if re.search(r"position\s*:\s*fixed", css):
            warns.append("uses position:fixed — only allowed for an intentional "
                         "full-screen modal")
        if "font-family:inherit" not in css.replace(" ", ""):
            fails.append("form controls need font-family:inherit to pick up the brand font")
        if "Interstate Condensed" not in css:
            fails.append("brand font 'Interstate Condensed' is not declared")
        if "min-height:44px" not in css.replace(" ", ""):
            warns.append("no 44px minimum tap target found — check touch targets")
        if "max-height:85svh" not in css.replace(" ", ""):
            warns.append("root is not a bounded 85svh panel — long lists will scroll the page")
        if "min-width:641px" not in css.replace(" ", ""):
            warns.append("no min-width:641px enhancement — is this really mobile-first?")

        found = set(re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", css))
        off = {c.lower() for c in found} - BRAND_COLORS
        # the heatmap ramp is intentionally interpolated between brand endpoints
        off = {c for c in off if c not in {"#f7f8fa", "#f6e0dd", "#eeb4ac", "#e07a70",
                                          "#7a0000", "#fff5f5", "#e3e8ee"}}
        if off:
            warns.append("colors outside the brand palette: " + ", ".join(sorted(off)))

    if scripts:
        js = scripts[0]
        for api in ("localStorage", "sessionStorage", "document.write"):
            if api in js:
                fails.append(f"uses {api} — not permitted in an embed")
        if re.search(r"\bapi[_-]?key\b|secret|Bearer ", js, re.I):
            fails.append("looks like it contains a credential — embeds must stay public-only")
        if "SFA:PRELOAD:START" not in src:
            warns.append("no crawlable preload block — search engines will see an empty tool")

    label = str(path.relative_to(REPO_ROOT)) if REPO_ROOT in path.parents else str(path)
    print(("FAIL  " if fails else "ok    ") + label)
    for f in fails:
        print("      x " + f)
    for w in warns:
        print("      ! " + w)
    return not fails


def main():
    args = sys.argv[1:]
    paths = [Path(a) for a in args] if args else sorted(
        (REPO_ROOT / "tools").glob("*/tool.html"))
    if not paths:
        print("no tool.html files found")
        return 1
    return 0 if all(lint(p) for p in paths) else 1


if __name__ == "__main__":
    sys.exit(main())
