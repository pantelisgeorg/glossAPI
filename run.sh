#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

.venv/bin/python - <<'PY'
from datetime import datetime
from pathlib import Path
from glossapi import Corpus

in_dir = Path("pdf_in")
supported_exts = {".pdf", ".md", ".docx", ".html", ".pptx", ".csv", ".xml"}
non_pdf_exts = supported_exts - {".pdf"}
inputs = sorted(
    p for p in in_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported_exts
)

# One run = one output folder. Single file -> named after it; many -> timestamp.
if len(inputs) == 1:
    out_dir = Path("artifacts") / inputs[0].stem
else:
    out_dir = Path("artifacts") / f"run_{datetime.now():%Y%m%d_%H%M%S}"

# The safe (pypdfium) backend only handles PDF; non-PDF formats need Docling.
backend = "safe" if all(p.suffix.lower() == ".pdf" for p in inputs) else "docling"

c = Corpus(in_dir, out_dir)
c.extract(input_format="all", phase1_backend=backend)
c.clean()
c.section()
c.annotate()
c.jsonl(out_dir / "export.jsonl")

print(f"\nDONE -> {out_dir}")
print("  view:  .venv/bin/python view_parquets.py " + str(out_dir))
PY
