#!/usr/bin/env python
"""Pipeline entrypoint used by the web UI (mirrors run.sh exactly).

Usage:
  python ui/pipeline_main.py [IN_DIR] [ARTIFACTS_DIR] [BACKEND] [--fix-headings]

- IN_DIR       folder with the source files (default: pdf_in)
- ARTIFACTS_DIR  root output folder (default: artifacts)
- BACKEND      auto | safe | docling  (default: auto)
- --fix-headings  rewrite `**bold**` heading lines in the generated
                  clean_markdown/ between the clean and section stages —
                  for PDFs whose headings come out as bold lines.

One run = one output folder: a single file is named after its stem, a batch
gets a `run_<timestamp>` folder. The safe (pypdfium) backend only handles
PDF; non-PDF inputs need Docling. `auto` picks like run.sh does.

Always prints `__GLOSSAPI_UI_EXIT__=<code>` as the final line so the UI job
runner can tell success from failure even across process boundaries.
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

SUPPORTED_EXTS = {".pdf", ".md", ".docx", ".html", ".pptx", ".csv", ".xml"}


def collect_inputs(in_dir: Path):
    return sorted(
        p for p in in_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def run(in_dir: Path, artifacts_dir: Path, backend: str = "auto",
        fix_headings: bool = False) -> int:
    inputs = collect_inputs(in_dir)
    if not inputs:
        print(f"No supported files ({', '.join(sorted(SUPPORTED_EXTS))}) found in {in_dir}")
        return 2

    # One run = one output folder. Single file -> named after it; many -> timestamp.
    if len(inputs) == 1:
        out_dir = artifacts_dir / inputs[0].stem
    else:
        out_dir = artifacts_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}"

    if backend == "auto":
        backend = "safe" if all(p.suffix.lower() == ".pdf" for p in inputs) else "docling"

    print(f"Inputs: {len(inputs)} file(s) from {in_dir}")
    print(f"Backend: {backend}")
    print(f"Output: {out_dir}")

    from glossapi import Corpus  # imported here so --help-style errors stay fast

    c = Corpus(in_dir, out_dir)
    c.extract(input_format="all", phase1_backend=backend)
    c.clean()

    if fix_headings:
        # PDFs only become markdown during extraction, so heading repair for
        # them happens here: on the generated clean_markdown, before section().
        # fix_headings.py lives at the repo root — importable, no subprocess.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import fix_headings as fh

        md_dir = out_dir / "clean_markdown"
        n = sum(fh.fix_file(p, apply=True, verbose=False) for p in sorted(md_dir.glob("*.md")))
        print(f"fix_headings: {n} bold heading line(s) rewritten in {md_dir}")

    c.section()
    c.annotate()
    c.jsonl(out_dir / "export.jsonl")

    print(f"\nDONE -> {out_dir}")
    return 0


def main() -> int:
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(pos) > 3 or any(f not in ("--fix-headings",) for f in flags):
        print(__doc__)
        return 2
    in_dir = Path(pos[0]) if len(pos) > 0 else Path("pdf_in")
    artifacts_dir = Path(pos[1]) if len(pos) > 1 else Path("artifacts")
    backend = pos[2] if len(pos) > 2 else "auto"
    if backend not in {"auto", "safe", "docling"}:
        print(f"Unknown backend: {backend} (use auto | safe | docling)")
        return 2
    fix_headings = "--fix-headings" in flags
    code = 1
    try:
        code = run(in_dir, artifacts_dir, backend, fix_headings=fix_headings)
    except Exception:
        print("ERROR: pipeline failed")
        traceback.print_exc()
        code = 1
    finally:
        print(f"__GLOSSAPI_UI_EXIT__={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
