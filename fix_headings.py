#!/usr/bin/env python
"""Convert full-line bold/italic paragraphs to markdown ## headings.

GlossAPI's sectioner only splits on `#` headings. Ebook-style markdown often
uses standalone `**Heading**` (or `*Heading*`) lines instead. This rewrites
those lines to `## Heading`.

Usage:
  python fix_headings.py [FOLDER]             dry-run: show what would change
  python fix_headings.py FOLDER --apply       write the changes
  python fix_headings.py FOLDER --italic      also convert *Heading* lines
  python fix_headings.py FOLDER --ext .md     file pattern (default .md)
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

changed = 0
for path in sorted(FOLDER.rglob(f"*{EXT}")):
    if ".tmp" in path.parts:
        continue
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    dirty = False
    for line in lines:
        text = line.rstrip("\n")
        m = BOLD.match(text)
        if m:
            new = f"## {m.group(1)}"
        elif ITALIC and (m := ITALIC_RE.match(text)):
            new = f"## {m.group(1)}"
        else:
            out.append(line)
            continue
        print(f"  {path}: {text.strip()[:70]}  ->  {new[:70]}")
        out.append(new + "\n")
        dirty = True
        changed += 1
    if dirty and APPLY:
        path.write_text("".join(out), encoding="utf-8")

print(f"\n{changed} heading(s) {'rewritten' if APPLY else 'would be rewritten (dry-run; add --apply)'}")
