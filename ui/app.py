"""glossAPI web UI entry point.

Run it from the repo root with:
  streamlit run ui/app.py

Pages:
  - Run pipeline   : manage pdf_in/ inputs, start/monitor/cancel a run
  - Runs browser   : explore artifacts/<run>/ (parquets, markdown, exports)
  - Tools          : fix_headings / parquets_to_db / sections_to_obsidian
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from ui import page_run, page_runs, page_tools


def main() -> None:
    st.set_page_config(
        page_title="glossAPI",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="auto",
    )

    pages = [
        st.Page(page_run.render, title="Run pipeline", url_path="run",
                icon=":material/play_arrow:", default=True),
        st.Page(page_runs.render, title="Runs browser", url_path="runs",
                icon=":material/folder_open:"),
        st.Page(page_tools.render, title="Tools", url_path="tools",
                icon=":material/build:"),
    ]
    pg = st.navigation(pages)
    pg.run()  # required: executes the selected st.Page function

    with st.sidebar:
        st.divider()
        st.caption(
            "glossAPI fork · pipeline: extract → clean → section → annotate → jsonl"
        )


if __name__ == "__main__":
    main()
