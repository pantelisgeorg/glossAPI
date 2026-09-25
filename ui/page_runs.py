"""Runs browser page: explore any artifacts/<run>/ — tables, markdown, exports."""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import runner

ARTIFACTS = runner.REPO_ROOT / "artifacts"
LONG_CELL = 200  # display truncation for long strings


def list_runs():
    """Run folders under artifacts/, newest first (skips hidden/utility dirs)."""
    if not ARTIFACTS.exists():
        return []
    runs = []
    for p in ARTIFACTS.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        if not ((p / "export.jsonl").exists() or any(p.rglob("*.parquet"))):
            continue
        runs.append(p)
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


@st.cache_data(ttl=10)
def load_parquet(path_str: str) -> pd.DataFrame:
    return pd.read_parquet(path_str)


def display_frame(df: pd.DataFrame, show_full: bool) -> pd.DataFrame:
    if show_full:
        return df
    view = df.copy()
    for col in view.columns:
        if view[col].dtype == object:
            view[col] = view[col].map(
                lambda v: (
                    f"{str(v)[:LONG_CELL]} … [{len(str(v))} chars]"
                    if isinstance(v, str) and len(v) > LONG_CELL else v
                )
            )
    return view


def overview_tab(run_dir: Path):
    metrics_p = run_dir / "download_results" / "download_results.parquet"
    if metrics_p.exists():
        df = load_parquet(str(metrics_p))
        st.subheader("Per-file metrics (download_results.parquet)")
        st.dataframe(df, width="stretch", hide_index=True)
        for col in ("needs_ocr", "filter"):
            if col in df.columns:
                counts = df[col].value_counts(dropna=False)
                st.write(f"**{col}** counts: " + " · ".join(f"{k}: {v}" for k, v in counts.items()))
    else:
        st.info("No metrics parquet in this run.")

    st.subheader("Run folder contents")
    lines = []
    for p in sorted(run_dir.rglob("*")):
        lines.append(("📁 " if p.is_dir() else "📄 ") + str(p.relative_to(run_dir)))
    with st.expander(f"{len(lines)} entries", expanded=False):
        st.code("\n".join(lines) or "(empty)", language="text")

def tables_tab(run_dir: Path):
    parquets = [
        p for p in sorted(run_dir.rglob("*.parquet"))
        if ".tmp" not in p.parts
    ]
    if not parquets:
        st.info("No parquet tables in this run.")
        return
    sel = st.selectbox(
        "Table",
        parquets,
        format_func=lambda p: str(p.relative_to(run_dir)),
    )
    df = load_parquet(str(sel))
    show_full = st.checkbox("Show long text columns in full", value=False)
    st.caption(f"{len(df)} rows × {len(df.columns)} cols")
    event = st.dataframe(
        display_frame(df, show_full),
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        height=350,
        key="parquet_table",
    )
    rows = event.selection.rows if event.selection else []
    if not rows:
        st.caption("Select a row in the table above to read its full text.")
        return
    for idx in rows:
        row = df.iloc[idx]
        st.markdown(f"**Row {idx}** — full contents")
        for col in df.columns:
            val = row[col]
            if not isinstance(val, str) or len(val) <= LONG_CELL:
                continue
            with st.expander(f"{col} ({len(val)} chars)"):
                st.markdown(val)
        st.divider()


def markdown_tab(run_dir: Path):
    raw_dir, clean_dir = run_dir / "markdown", run_dir / "clean_markdown"
    stems = {}
    for d, tag in ((raw_dir, "raw"), (clean_dir, "clean")):
        if d.exists():
            for p in d.glob("*.md"):
                stems.setdefault(p.stem, {})[tag] = p
    if not stems:
        st.info("No markdown outputs in this run.")
        return
    stem = st.selectbox("Document", sorted(stems), key="md_stem")
    pair = stems[stem]
    left, right = st.columns(2)
    with left:
        st.subheader("Raw markdown (extract)")
        p = pair.get("raw")
        if p:
            text = p.read_text(encoding="utf-8", errors="replace")
            st.markdown(text)
            st.download_button("Download raw .md", text, file_name=p.name)
        else:
            st.caption("(missing)")
    with right:
        st.subheader("Cleaned markdown (clean)")
        p = pair.get("clean")
        if p:
            text = p.read_text(encoding="utf-8", errors="replace")
            st.markdown(text)
            st.download_button("Download clean .md", text, file_name=p.name)
        else:
            st.caption("(missing)")


def export_tab(run_dir: Path):
    jsonl = run_dir / "export.jsonl"
    if jsonl.exists():
        st.subheader("export.jsonl")
        data = jsonl.read_text(encoding="utf-8", errors="replace")
        lines = [ln for ln in data.splitlines() if ln.strip()]
        st.caption(f"{len(lines)} records")
        for ln in lines[:5]:
            try:
                st.json(json.loads(ln))
            except json.JSONDecodeError:
                st.code(ln[:500], language="text")
        if len(lines) > 5:
            st.caption(f"… and {len(lines) - 5} more")
        st.download_button(
            "Download export.jsonl", data, file_name="export.jsonl", mime="text/plain"
        )
    else:
        st.info("No export.jsonl in this run.")

    st.subheader("Download any parquet as CSV")
    parquets = [p for p in sorted(run_dir.rglob("*.parquet")) if ".tmp" not in p.parts]
    for p in parquets:
        if st.button(f"📦 {p.relative_to(run_dir)}", key=f"csv_{p.name}_{p.stat().st_mtime}"):
            csv_text = load_parquet(str(p)).to_csv(index=False)
            st.download_button(
                "⬇ Download CSV",
                csv_text,
                file_name=p.stem + ".csv",
                mime="text/csv",
                key=f"dld_{p.name}",
            )


def render():
    st.header("📁 Runs browser")
    st.caption("Every pipeline run writes its own folder under `artifacts/`.")

    runs = list_runs()
    if not runs:
        st.info("No runs found under `artifacts/`. Start one on the **Run pipeline** page.")
        return

    options = {
        f"{p.name}  ({time.strftime('%Y-%m-%d %H:%M', time.localtime(p.stat().st_mtime))})": p
        for p in runs
    }
    label = st.selectbox("Run", list(options))
    run_dir = options[label]

    tabs = st.tabs(["Overview", "Tables", "Markdown", "Export"])
    with tabs[0]:
        overview_tab(run_dir)
    with tabs[1]:
        tables_tab(run_dir)
    with tabs[2]:
        markdown_tab(run_dir)
    with tabs[3]:
        export_tab(run_dir)
