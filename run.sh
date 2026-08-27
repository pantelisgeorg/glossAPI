#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

.venv/bin/python - <<'PY'
from pathlib import Path
from glossapi import Corpus

in_dir = Path("pdf_in")
non_pdf_exts = {".md", ".docx", ".html", ".pptx", ".csv", ".xml"}
has_non_pdf = any(
    p.suffix.lower() in non_pdf_exts for p in in_dir.rglob("*") if p.is_file()
)
# The safe (pypdfium) backend only handles PDF; non-PDF formats need Docling.
backend = "docling" if has_non_pdf else "safe"

c = Corpus(in_dir, Path("artifacts"))
c.extract(input_format="all", phase1_backend=backend)
c.clean()
c.section()
c.annotate()
c.jsonl(Path("artifacts/export.jsonl"))
PY
