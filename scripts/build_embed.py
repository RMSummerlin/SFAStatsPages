#!/usr/bin/env python3
"""
Generate the paste-ready copy of each tool fragment.

Each tool ships two files:

    tools/<name>/tool.html    the working copy, with all the development notes
    tools/<name>/embed.html   the same fragment with every comment removed

`embed.html` is what goes into the Avada Code Block. Anyone hitting Ctrl+U on a
published article sees the markup either way, so the notes explaining why a
median is used instead of a mean, or which Avada rule a workaround exists for,
should not be in the copy that ships.

Only comments are removed. No minification, no renaming, no reordering — the two
files differ by deletions and nothing else, so a diff between them stays readable
and a bug reproduced in one reproduces in the other.

Comments are found with a state machine rather than regular expressions, because
`//` also occurs inside the GitHub Pages URL, and `/*` can occur inside a string
or a regex literal. A regex-based stripper eats those and ships a broken tool.

Named build_* so neither the pull glob (`pull_*.py`) nor the test glob
(`test_*.py`) in the workflow picks it up. This runs by hand, at delivery time.

  python scripts/build_embed.py            # rewrite every tools/*/embed.html
  python scripts/build_embed.py --check    # exit 1 if any is stale, write nothing
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"

# Comments are blanked to this sentinel first. A line left holding nothing but
# sentinels and whitespace was a comment line and is deleted outright; a
# sentinel with code beside it was a trailing comment and just goes away.
MARK = "\x00"

# Newlines inside a template literal are content, not layout. They are swapped
# for this sentinel while the file is being tidied so that trimming trailing
# whitespace and collapsing blank lines cannot reach inside one, then swapped
# back. Without it, a multi-line template literal comes out with its indentation
# silently altered.
KEEP_NL = "\x02"

BLOCK_RE = re.compile(
    r"<(?P<tag>style|script)\b[^>]*>(?P<body>.*?)</(?P=tag)\s*>",
    re.S | re.I,
)


# ------------------------------------------------------------------ strippers


def strip_html(text: str) -> str:
    """Blank <!-- --> comments. Conditional comments are not used here."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            if end == -1:
                # Unterminated. Leave the rest alone rather than eat the file.
                out.append(text[i:])
                break
            out.append(MARK)
            i = end + 3
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def strip_css(text: str) -> str:
    """Blank /* */ comments, leaving quoted strings and url() intact."""
    out = []
    i = 0
    n = len(text)
    quote = ""
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                out.append(text[i:])
                break
            out.append(MARK)
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# A '/' opens a regex literal unless the previous meaningful token could end an
# expression. Identifiers, numbers, ')', ']' and the keywords that behave like
# values all mean division; everything else — operators, '(', ',', 'return',
# 'typeof' — means a regex is starting.
VALUE_END_RE = re.compile(r"(?:[\w$)\]]|\+\+|--)$")
KEYWORD_RE = re.compile(r"(?:^|[^\w$])(return|typeof|instanceof|in|of|new|delete|void|case|do|else|yield|throw)$")


def _regex_allowed(prev: str) -> bool:
    """Given the code emitted so far, can a '/' here start a regex literal?"""
    stripped = prev.rstrip()
    if not stripped:
        return True
    if KEYWORD_RE.search(stripped):
        return True
    return not VALUE_END_RE.search(stripped)


def strip_js(text: str) -> str:
    """Blank // and /* */ comments, leaving strings, templates and regexes intact."""
    out: list[str] = []
    i = 0
    n = len(text)
    # Stack of template-literal depths, so `${ {a:`x`} }` nests correctly.
    template_stack: list[int] = []
    brace_depth = 0

    while i < n:
        ch = text[i]

        # ---- line comment
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            end = text.find("\n", i)
            out.append(MARK)
            i = n if end == -1 else end
            continue

        # ---- block comment
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                out.append(text[i:])
                break
            out.append(MARK)
            i = end + 2
            continue

        # ---- quoted string
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                if c == quote:
                    break
            continue

        # ---- template literal
        if ch == "`":
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append(c)
                    out.append(text[i + 1])
                    i += 2
                    continue
                if c == "`":
                    out.append(c)
                    i += 1
                    break
                if c == "$" and i + 1 < n and text[i + 1] == "{":
                    out.append("${")
                    i += 2
                    template_stack.append(brace_depth)
                    brace_depth += 1
                    break
                out.append(KEEP_NL if c == "\n" else c)
                i += 1
            continue

        # ---- brace tracking, so a template's ${...} knows where it ends
        if ch == "{":
            brace_depth += 1
            out.append(ch)
            i += 1
            continue
        if ch == "}":
            brace_depth -= 1
            if template_stack and brace_depth == template_stack[-1]:
                template_stack.pop()
                out.append("}")
                i += 1
                # Back inside the template's text run.
                while i < n:
                    c = text[i]
                    if c == "\\" and i + 1 < n:
                        out.append(c)
                        out.append(text[i + 1])
                        i += 2
                        continue
                    if c == "`":
                        out.append(c)
                        i += 1
                        break
                    if c == "$" and i + 1 < n and text[i + 1] == "{":
                        out.append("${")
                        i += 2
                        template_stack.append(brace_depth)
                        brace_depth += 1
                        break
                    out.append(KEEP_NL if c == "\n" else c)
                    i += 1
                continue
            out.append(ch)
            i += 1
            continue

        # ---- regex literal
        if ch == "/" and _regex_allowed("".join(out).replace(MARK, "")):
            out.append(ch)
            i += 1
            in_class = False
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                elif c == "\n":
                    break  # not a regex after all; bail rather than run away
            continue

        out.append(ch)
        i += 1

    return "".join(out)


# ------------------------------------------------------------------- assembly


def tidy(text: str) -> str:
    """Drop comment-only lines, trailing whitespace and runs of blank lines."""
    lines = []
    for line in text.split("\n"):
        if MARK in line and not line.replace(MARK, "").strip():
            continue  # the whole line was a comment
        lines.append(line.replace(MARK, "").rstrip())

    out = []
    for line in lines:
        if not line and out and not out[-1]:
            continue  # never two blank lines in a row
        out.append(line)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out).replace(KEEP_NL, "\n") + "\n"


def strip_fragment(html: str) -> str:
    """Remove every comment from a tool fragment, changing nothing else."""
    for sentinel, name in ((MARK, "MARK"), (KEEP_NL, "KEEP_NL")):
        if sentinel in html:
            raise SystemExit(
                f"Fragment already contains the {name} sentinel byte "
                f"{sentinel!r}. Pick a different one in build_embed.py.")
    pieces = []
    pos = 0
    for m in BLOCK_RE.finditer(html):
        pieces.append(strip_html(html[pos:m.start()]))
        body = m.group("body")
        stripper = strip_css if m.group("tag").lower() == "style" else strip_js
        pieces.append(html[m.start():m.start("body")])
        pieces.append(stripper(body))
        pieces.append(html[m.end("body"):m.end()])
        pos = m.end()
    pieces.append(strip_html(html[pos:]))
    return tidy("".join(pieces))


# ----------------------------------------------------------------- validation


def script_bodies(html: str):
    return [m.group("body") for m in BLOCK_RE.finditer(html)
            if m.group("tag").lower() == "script"]


def js_literals(html: str) -> list[str]:
    """Every string and template literal in the fragment's script blocks."""
    found = []
    for body in script_bodies(html):
        i, n = 0, len(body)
        while i < n:
            ch = body[i]
            if ch == "/" and i + 1 < n and body[i + 1] == "/":
                end = body.find("\n", i)
                i = n if end == -1 else end
                continue
            if ch == "/" and i + 1 < n and body[i + 1] == "*":
                end = body.find("*/", i + 2)
                i = n if end == -1 else end + 2
                continue
            if ch in "\"'`":
                quote, start, i = ch, i, i + 1
                while i < n:
                    c = body[i]
                    if c == "\\":
                        i += 2
                        continue
                    i += 1
                    if c == quote:
                        break
                    if c == "\n" and quote != "`":
                        break
                found.append(body[start:i])
                continue
            i += 1
    return found


def validate(original: str, stripped: str, label: str) -> list[str]:
    """Every check that would catch a stripper that ate real code."""
    problems = []

    # 1. Idempotent: a second pass must find nothing left to remove.
    if strip_fragment(stripped) != stripped:
        problems.append("second strip pass changed the file again")

    # 2. The JS still parses.
    for idx, body in enumerate(script_bodies(stripped)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(body)
            tmp = fh.name
        try:
            res = subprocess.run(["node", "--check", tmp],
                                 capture_output=True, text=True)
            if res.returncode != 0:
                first = (res.stderr.strip().split("\n") or [""])[0]
                problems.append(f"script block {idx} does not parse: {first}")
        except FileNotFoundError:
            problems.append("node not available — could not syntax-check the script")
            break
        finally:
            Path(tmp).unlink(missing_ok=True)

    # 3. Nothing but comments went. Compare the non-comment characters of the
    #    original against the output, whitespace ignored.
    def bones(text):
        return re.sub(r"\s+", "", strip_fragment(text).replace(MARK, ""))

    if bones(original) != bones(stripped):
        problems.append("non-comment characters differ from the original")

    # 4. Every URL survived, since '//' is where a naive stripper fails.
    for url in set(re.findall(r"https?://[^\s\"'`)]+", original)):
        if url not in stripped:
            problems.append(f"URL lost: {url}")

    # 5. Every string and template literal is byte-identical. Check 3 ignores
    #    whitespace, so on its own it would not notice tidy() trimming a line
    #    inside a multi-line template literal, where the whitespace is content.
    #    Neither current tool uses one; this is here so the first tool that does
    #    fails loudly rather than shipping a fragment with mangled output.
    before, after = js_literals(original), js_literals(stripped)
    if before != after:
        lost = [s for s in before if s not in after][:3]
        problems.append("string/template literals changed: "
                        + ("; ".join(repr(s[:60]) for s in lost) or "count differs"))

    return problems


# ---------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report stale embed.html files without writing")
    args = ap.parse_args()

    tools = sorted(p for p in TOOLS_DIR.glob("*/tool.html"))
    if not tools:
        print("No tools/*/tool.html found.")
        return 1

    failures = 0
    stale = 0
    for tool in tools:
        rel = tool.relative_to(REPO_ROOT).as_posix()
        original = tool.open(encoding="utf-8", newline="").read()
        stripped = strip_fragment(original.replace("\r\n", "\n"))

        problems = validate(original.replace("\r\n", "\n"), stripped, rel)
        if problems:
            failures += 1
            print(f"FAIL  {rel}")
            for p in problems:
                print(f"      {p}")
            continue

        target = tool.with_name("embed.html")
        current = (target.open(encoding="utf-8", newline="").read()
                   if target.exists() else None)
        saved = len(original) - len(stripped)

        if current == stripped:
            print(f"ok    {rel} — embed.html already current")
            continue

        if args.check:
            stale += 1
            print(f"STALE {rel} — embed.html does not match")
            continue

        target.open("w", encoding="utf-8", newline="").write(stripped)
        print(f"ok    {rel} → {target.name} "
              f"({saved:,} bytes of notes removed, {len(stripped):,} left)")

    if failures:
        print(f"\n{failures} fragment(s) failed validation. Nothing written for those.")
        return 1
    if stale:
        print(f"\n{stale} embed.html file(s) out of date. "
              f"Run scripts/build_embed.py without --check.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
