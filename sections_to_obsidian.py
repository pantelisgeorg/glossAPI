#!/usr/bin/env python
"""Convert a glossAPI run into an Obsidian vault / knowledge base.

The vault is a PERSISTENT knowledge base: runs are MERGED into it by
default — new documents are added, documents that already exist are
updated in place (their section notes are regenerated), and index.md is
rebuilt from every document in the vault. Nothing from other runs is
touched. Use --fresh to wipe the vault and start over.

Vault layout:
  index.md                     corpus overview + links to all documents
  <doc>.md                     whole document (all sections, with headings)
  sections/<doc>/<n> <h>.md    one note per section, pipeline metadata
                               in YAML frontmatter, wikilinks back to the doc

Usage:
  python sections_to_obsidian.py [RUN_DIR] [VAULT_DIR] [--fresh]

Defaults: RUN_DIR = latest artifacts/*/ run, VAULT_DIR = vault/
"""
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

ARTIFACTS = Path("artifacts")
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
RUN_DIR = Path(_args[0]) if _args else None
VAULT_DIR = Path(_args[1]) if len(_args) > 1 else Path("vault")
FRESH = "--fresh" in sys.argv
# --merge is accepted for compatibility; merging is the default now.


def safe_name(text: str, max_len: int = 60) -> str:
    name = re.sub(r"[\\/:*?\"<>|#^\[\]]+", " ", text or "section")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len] or "section"


def strip_ext(name: str) -> str:
    """Strip known document extensions without mangling dots in the stem
    (e.g. '13.Plato's Republic.md' -> \"13.Plato's Republic\")."""
    return re.sub(r"\.(md|pdf|docx|html|txt|xml|csv)$", "", name, flags=re.IGNORECASE)


def natural_key(name: str):
    """Sort key: '5.1 the Sofists' -> (5.1, 'the Sofists'), '12.Plato' -> (12, 'Plato')."""
    m = re.match(r"^(\d+(?:\.\d+)?)[.\s-]*(.*)$", name)
    if m:
        return (float(m.group(1)), m.group(2).lower())
    return (float("inf"), name.lower())


def doc_tag(name: str) -> str:
    """Short unique prefix for a document, e.g. '5.1 the Sofists' -> '5.1'."""
    m = re.match(r"^(\d+(?:\.\d+)?)[.\s-]+", name)
    return m.group(1) if m else safe_name(name, max_len=10)


def frontmatter(fields: dict) -> str:
    body = yaml.safe_dump(fields, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{body}---\n"


def read_frontmatter(path: Path) -> dict:
    """YAML frontmatter of a note ('---\\n...\\n---') as a dict."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                return yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                return {}
    return {}


def rebuild_index(vault: Path) -> int:
    """Rebuild index.md from every doc note currently in the vault."""
    docs = []
    for p in sorted(vault.glob("*.md")):
        if p.name == "index.md":
            continue
        fm = read_frontmatter(p)
        docs.append((str(fm.get("source") or p.name), fm.get("sections", "?")))
    ordered = sorted(docs, key=lambda d: natural_key(strip_ext(d[0])))
    lines = [
        "# Corpus index\n",
        "> glossAPI knowledge base — documents merged from pipeline runs.\n",
        "## Documents\n",
    ]
    for source, n in ordered:
        stem = strip_ext(source)
        lines.append(f"- [[{safe_name(stem)}|{stem}]] ({n} sections)")
    lines.append(f"\n{len(docs)} documents in the knowledge base.")
    (vault / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(docs)


def main() -> None:
    if RUN_DIR is None:
        runs = [
            p for p in ARTIFACTS.glob("*")
            if p.is_dir() and (p / "sections" / "sections_for_annotation.parquet").exists()
        ]
        if not runs:
            print("No pipeline runs found under artifacts/")
            sys.exit(1)
        RUN = max(runs, key=lambda p: p.stat().st_mtime)
    else:
        RUN = Path(RUN_DIR)

    sections_p = RUN / "sections" / "sections_for_annotation.parquet"
    metrics_p = RUN / "download_results" / "download_results.parquet"
    if not sections_p.exists():
        print(f"No sections parquet in {RUN}")
        sys.exit(1)

    sections = pd.read_parquet(sections_p)
    metrics = pd.read_parquet(metrics_p) if metrics_p.exists() else pd.DataFrame()
    if not metrics.empty:
        key = "filename_base" if "filename_base" in metrics.columns else "filename"
        metrics[key] = metrics[key].astype(str).map(strip_ext)
    classified_p = RUN / "classified_sections.parquet"
    classified = pd.read_parquet(classified_p) if classified_p.exists() else pd.DataFrame()
    if not classified.empty and "id" in classified.columns and "predicted_section" in classified.columns:
        sections = sections.merge(
            classified[["id", "predicted_section"]], on="id", how="left"
        )
    metric_cols = [c for c in ["greek_badness_score", "percentage_greek",
                               "polytonic_ratio", "filter", "needs_ocr", "file_ext"]
                   if c in metrics.columns]

    vault = VAULT_DIR
    if FRESH and vault.exists():
        shutil.rmtree(vault)
        print(f"--fresh: wiped {vault}")
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "sections").mkdir(exist_ok=True)

    # documents already in the knowledge base (for added/updated accounting)
    existing = {p.stem for p in vault.glob("*.md") if p.name != "index.md"}
    added = updated = 0
    section_count = 0

    ordered = sorted(sections["filename"].astype(str).unique(), key=lambda f: natural_key(strip_ext(f)))
    for filename in ordered:
        group = sections[sections["filename"] == filename]
        stem = strip_ext(str(filename))
        tag = doc_tag(stem)
        if safe_name(stem) in existing:
            updated += 1
        else:
            added += 1
        doc_dir = vault / "sections" / safe_name(stem)
        if doc_dir.exists():
            shutil.rmtree(doc_dir)  # drop stale section notes from older versions
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc_note = vault / f"{safe_name(stem)}.md"

        m_row = None
        if not metrics.empty:
            m = metrics[metrics["filename_base"] == stem]
            m_row = m.iloc[0] if not m.empty else None
        stats = {}
        if m_row is not None:
            for c in metric_cols:
                v = m_row[c]
                if pd.isna(v):
                    stats[c] = None
                else:
                    stats[c] = v.item() if hasattr(v, "item") else v

        doc_lines = [frontmatter({
            "source": filename,
            "sections": int(len(group)),
            "tags": ["document"],
            **stats,
        }), f"# {stem}\n"]

        for i, (_, row) in enumerate(group.iterrows(), 1):
            section_count += 1
            # Full heading for display (H1, wikilink aliases, frontmatter);
            # a filesystem-safe truncated stem only for the note FILENAME.
            full_heading = (
                re.sub(r"\s+", " ", str(row.get("header", "")).strip("* ")).strip(" .")
                or f"Section {i}"
            )
            heading = safe_name(full_heading, max_len=80)
            note_name = f"{tag}. {i:02d} {heading}"
            note_path = doc_dir / f"{note_name}.md"
            fm = {
                "source": filename,
                "heading": str(row.get("header", "")),
                "place": str(row.get("place", "")),
                "predicted_section": str(row.get("predicted_section", "")),
                "has_text": bool(row.get("has_text", False)),
                "has_list": bool(row.get("has_list", False)),
                "has_table": bool(row.get("has_table", False)),
                "tags": ["section"],
            }
            if m_row is not None:
                fm.update(stats)
            text = str(row.get("section", ""))
            note_path.write_text(
                frontmatter(fm)
                + f"# {full_heading}\n\n"
                + f"*Source: [[{safe_name(stem)}]] — pages {fm['place']}*\n\n"
                + text + "\n",
                encoding="utf-8",
            )
            doc_lines.append(f"{i}. [[sections/{safe_name(stem)}/{note_name}|{full_heading}]]")

        doc_note.write_text("\n\n".join(doc_lines) + "\n", encoding="utf-8")

    total_docs = rebuild_index(vault)

    print(f"Knowledge base: {added} new document(s), {updated} updated "
          f"({section_count} section notes written this run)")
    print(f"Vault now holds {total_docs} document(s) -> {vault}/")
    print("Open the folder as an Obsidian vault and start from index.md")


if __name__ == "__main__":
    main()
