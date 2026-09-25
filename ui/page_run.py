"""Run page: put files in pdf_in/, start the pipeline, watch the live log."""
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui import runner

REPO_ROOT = runner.REPO_ROOT
PDF_IN = REPO_ROOT / "pdf_in"
SUPPORTED_EXTS = [".pdf", ".md", ".docx", ".html", ".pptx", ".csv", ".xml"]
SUPPORTED_LABELS = [e.lstrip(".") for e in SUPPORTED_EXTS]


def input_files():
    if not PDF_IN.exists():
        return []
    return sorted(
        p for p in PDF_IN.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


@st.fragment(run_every=2)
def status_fragment():
    cur = runner.status()
    state = cur["state"]
    if state == "idle":
        st.info("No pipeline job recorded. Start a run above.")
        return
    job = cur["job"]
    minutes = (time.time() - job["started"]) / 60
    if state == "running":
        st.success(
            f"Pipeline running — pid {job['pid']} · backend `{job['backend']}` · "
            f"{minutes:.1f} min elapsed. Log refreshes every 2 s."
        )
    elif state == "done":
        st.success(f"✅ Run finished ({minutes:.1f} min). Browse it on the **Runs browser** page.")
        st.caption("Add its documents to your vault / knowledge base from the **Tools** page.")
    else:
        st.error("❌ Run failed. Check the log tail below.")
        if cur.get("note"):
            st.warning(cur["note"])
    with st.expander("Pipeline log (tail)", expanded=True):
        st.code(cur["log"] or "(no output yet)", language="text")


def render():
    st.header("▶ Run the pipeline")
    st.caption(
        "Files in `pdf_in/` are processed by extract → clean → section → "
        "annotate → jsonl. One run = one folder under `artifacts/`."
    )

    # --- input files -----------------------------------------------------
    st.subheader("Input files (pdf_in/)")
    files = input_files()
    if files:
        rows = [
            {"file": str(p.relative_to(PDF_IN)), "size KB": round(p.stat().st_size / 1024, 1)}
            for p in files
        ]
        import pandas as pd

        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.warning(f"No supported files in `{PDF_IN}` yet — upload some below.")

    uploads = st.file_uploader(
        "Upload source files (saved to pdf_in/)",
        accept_multiple_files=True,
        type=SUPPORTED_LABELS,
    )
    if uploads and st.button(f"Save {len(uploads)} uploaded file(s) to pdf_in/"):
        PDF_IN.mkdir(exist_ok=True)
        for f in uploads:
            (PDF_IN / f.name).write_bytes(f.getvalue())
        st.toast(f"Saved {len(uploads)} file(s) to pdf_in/")
        st.rerun()

    # --- backend + controls ----------------------------------------------
    st.subheader("Settings")
    backend = st.radio(
        "Phase-1 extraction backend",
        ["auto", "safe", "docling"],
        index=0,
        horizontal=True,
        help=(
            "auto: `safe` (pypdfium) if all inputs are PDF, else `docling` — same logic as run.sh. "
            "Non-PDF inputs always need `docling`."
        ),
    )

    fix_head = st.checkbox(
        "Fix **bold** headings after extraction (before sectioning)",
        value=False,
        help=(
            "PDFs only become markdown during extraction, and some come out "
            "with bold-only headings that the sectioner can't split on. This "
            "runs fix_headings.py on the generated clean_markdown/ between the "
            "clean and section stages — works for PDF and markdown inputs alike."
        ),
    )

    cur = runner.status()
    if cur["state"] == "running":
        if st.button("🛑 Cancel running job"):
            runner.cancel_job()
            st.rerun()
        st.caption("A job is already running; wait for it to finish or cancel it first.")
    else:
        if cur["state"] != "idle":
            if st.button("🧹 Clear finished job from the tracker"):
                runner.clear_finished_job()
                st.rerun()
        start = st.button(
            "🚀 Start run", type="primary", disabled=not files
        )
        if start:
            try:
                runner.start_job(PDF_IN, REPO_ROOT / "artifacts", backend,
                                 fix_headings=fix_head)
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))

    st.divider()
    status_fragment()
