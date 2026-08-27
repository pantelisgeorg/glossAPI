#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

.venv/bin/python - <<'PY'
from pathlib import Path
from glossapi import Corpus

c = Corpus(Path("pdf_in"), Path("artifacts"))
c.extract(input_format="all")
c.clean()
c.section()
c.jsonl(Path("artifacts/export.jsonl"))
PY
