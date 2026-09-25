#!/usr/bin/env python
"""Convert full-line bold/italic paragraphs to markdown ## headings.

GlossAPI's sectioner only splits on `#` headings. Ebook-style markdown often
uses standalone `**Heading**` (or `*Heading*`) lines instead. This rewrites
those lines to `## Heading`.

Usage:
  python fix_headings.py [FOLDER]             dry-run: show what would change
  python fix_headings.py FOLDER --apply       write the changes
  python fix_headings.py FOLDER --italic      also convert *Heading* lines
  python fix_headings.py FOLDER --ext=.md     file pattern (default .md)

Also usable as a module: `fix_file(path, italic, apply)` rewrites one file
and returns the number of changed lines. The web UI's "fix headings after
extraction" option uses this on the generated clean_markdown/ between the
clean and section stages.
"""
import re
import sys
from pathlib import Path

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
FOLDER = Path(POS[0]) if POS else Path("pdf_in")
APPLY = "--apply" in sys.argv
ITALIC = "--italic" in sys.argv
EXT = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--ext=")), ".md")

BOLD = re.compile(r"^\*\*(.+?)\*\*\s*$")
ITALIC_RE = re.compile(r"^\*(.+?)\*\s*$")
# Inline heading: **Heading words.** body text on the same line.
# Require 2+ words ending with a period and an uppercase/digit start so
# glossary entries like **μοῖρα** (...): definition are left untouched.
INLINE_HEADING = re.compile(r"^\*\*([^*]{3,90}\.)\*\*\s+(.+)$")


def rewrite_line(text: str, italic: bool = False):
    """If `text` is a heading-like bold/italic line, return (new_line, rest);
    otherwise (None, None). `rest` is trailing text split off an inline
    heading."""
    m = BOLD.match(text)
    if m:
        return f"## {m.group(1)}", None
    im = INLINE_HEADING.match(text) if not italic else None
    if im and (" " in im.group(1).strip()) and (
        im.group(1)[0].isupper() or im.group(1)[0].isdigit()
    ):
        return f"## {im.group(1)}", im.group(2).strip()
    if italic and (m := ITALIC_RE.match(text)):
        return f"## {m.group(1)}", None
    return None, None


def fix_file(path: Path, italic: bool = False, apply: bool = False,
             verbose: bool = True) -> int:
    """Rewrite heading-like lines in `path`; return the number of changes.

    Only writes the file when `apply=True` (dry-run by default, like the CLI).
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    changed = 0
    for line in lines:
        text = line.rstrip("\n")
        new, rest = rewrite_line(text, italic)
        if new is None:
            out.append(line)
            continue
        if verbose:
            print(f"  {path}: {text.strip()[:70]}  ->  {new[:70]}")
        out.append(new + "\n")
        if rest:
            out.append(rest + "\n")
        changed += 1
    if changed and apply:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def main() -> None:
    changed = 0
    for path in sorted(FOLDER.rglob(f"*{EXT}")):
        if ".tmp" in path.parts:
            continue
        changed += fix_file(path, italic=ITALIC, apply=APPLY)

    print(f"\n{changed} heading(s) {'rewritten' if APPLY else 'would be rewritten (dry-run; add --apply)'}")


if __name__ == "__main__":
    main()
