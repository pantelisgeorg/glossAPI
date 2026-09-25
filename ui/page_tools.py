"""Tools page: expose the fork's helper scripts with buttons, no CLI needed."""
import shutil
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import runner
from ui import page_runs

REPO_ROOT = runner.REPO_ROOT
JOBS_DIR = runner.JOBS_DIR
ARTIFACTS = runner.REPO_ROOT / "artifacts"


def build_combined_jsonl(root: Path):
    """Concatenate every run's export.jsonl under `root` into one file.

    Writes `root/export_all.jsonl` (rebuilt each call, never inside a run
    folder). Returns (record_count, runs_used, output_path).
    """
    jsonls = [p for p in sorted(root.glob("*/export.jsonl"))]
    lines = []
    for p in jsonls:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip():
                lines.append(ln)
    out = root / "export_all.jsonl"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines), len(jsonls), out


def jsonl_section():
    st.subheader("📦 Combined export.jsonl — one file for ALL runs")
    st.caption(
        "Each run keeps its own export.jsonl. This rebuilds "
        "`artifacts/export_all.jsonl` by concatenating them all — the "
        "cumulative training/export file for the whole knowledge base."
    )
    if st.button("Build combined export.jsonl"):
        count, runs, out = build_combined_jsonl(ARTIFACTS)
        if count == 0:
            st.info("No export.jsonl found under artifacts/ — run the pipeline first.")
        else:
            show_result(0, f"Merged {count} record(s) from {runs} run(s) -> {out}")
    out = ARTIFACTS / "export_all.jsonl"
    if out.exists():
        n = sum(
            1 for ln in out.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        )
        st.download_button(
            f"⬇ Download export_all.jsonl ({n} records)",
            data=out.read_bytes(),
            file_name="export_all.jsonl",
            mime="text/plain",
        )


def show_result(code: int, out: str) -> None:
    st.code(out or "(no output)", language="text")
    if code == 0:
        st.success("Done.")
    else:
        st.error(f"Exited with code {code}.")


def fix_headings_section():
    st.subheader("📝 fix_headings.py — turn **bold** lines into `##` headings")
    st.caption(
        "GlossAPI's sectioner only splits on `#` headings. Ebook-style markdown "
        "often uses standalone `**Heading**` lines; this rewrites them. Dry-run by default."
    )
    folder = st.text_input("Folder", value="pdf_in", key="fh_folder")
    italic = st.checkbox("Also convert *italic* lines (`--italic`)", value=False)
    mode = st.radio("Mode", ["Dry-run", "Apply (--apply)"], horizontal=True)
    if st.button("Run fix_headings"):
        args = ["fix_headings.py", folder]
        if italic:
            args.append("--italic")
        if mode.startswith("Apply"):
            args.append("--apply")
        code, out = runner.run_tool(args)
        show_result(code, out)


def duckdb_section():
    st.subheader("🦆 parquets_to_db.py — all parquets into one DuckDB file")
    st.caption("Open the result in DBeaver / TablePlus / DB Browser, or download it here.")
    folder = st.text_input("Folder", value="artifacts", key="db_folder")
    if st.button("Build DuckDB database"):
        code, out = runner.run_tool(["parquets_to_db.py", folder])
        show_result(code, out)
        if code == 0:
            st.session_state["duckdb_built"] = True
    db_path = Path(folder) / "glossapi.duckdb"
    if db_path.exists():
        size = db_path.stat().st_size / (1024 * 1024)
        st.download_button(
            f"⬇ Download {db_path.name} ({size:.1f} MB)",
            data=db_path.read_bytes(),
            file_name=db_path.name,
            mime="application/octet-stream",
        )


def obsidian_section():
    st.subheader("🗂 Knowledge base (Obsidian vault) — sections_to_obsidian.py")
    st.caption(
        "Runs are **merged** into the vault by default: new documents are added, "
        "same-name documents are updated in place, and index.md lists everything. "
        "Other documents are never touched — one knowledge base, no new vaults."
    )
    runs = page_runs.list_runs()
    if not runs:
        st.info("No runs under `artifacts/` yet.")
        return
    labels = ["(latest run — auto)"] + [str(r.relative_to(REPO_ROOT)) for r in runs]
    choice = st.selectbox("Run", labels, key="obs_run")
    vault_name = st.text_input("Vault folder (the knowledge base)", value="vault", key="obs_vault")
    mode = st.radio(
        "Mode",
        ["Add to knowledge base (merge)", "Rebuild vault from scratch"],
        horizontal=True,
        key="obs_mode",
    )
    if st.button("Add run to knowledge base" if mode.startswith("Add") else "Rebuild vault"):
        args = ["sections_to_obsidian.py"]
        if not choice.startswith("(latest"):
            args.append(choice)
        args.append(vault_name)
        if mode.startswith("Rebuild"):
            args.append("--fresh")
        code, out = runner.run_tool(args)
        show_result(code, out)
        if code == 0:
            st.session_state["vault_built"] = vault_name
    vault_dir = REPO_ROOT / vault_name
    if vault_dir.exists() and any(vault_dir.glob("*.md")):
        if st.button("📦 Zip vault for download", key="zip_vault"):
            JOBS_DIR.mkdir(parents=True, exist_ok=True)
            zip_base = JOBS_DIR / f"{vault_name}"
            zip_path = shutil.make_archive(
                str(zip_base), "zip", root_dir=str(REPO_ROOT), base_dir=vault_name
            )
            st.session_state["vault_zip"] = zip_path
        zip_path = st.session_state.get("vault_zip")
        if zip_path and Path(zip_path).exists():
            st.download_button(
                "⬇ Download vault .zip",
                data=Path(zip_path).read_bytes(),
                file_name=Path(zip_path).name,
                mime="application/zip",
            )


def render():
    st.header("🔧 Tools")
    st.caption("The fork's helper scripts, exposed as buttons. Output is captured live.")
    fix_headings_section()
    st.divider()
    duckdb_section()
    st.divider()
    obsidian_section()
    st.divider()
    jsonl_section()
