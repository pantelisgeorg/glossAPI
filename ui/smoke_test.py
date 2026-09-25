"""Smoke-test the Streamlit UI pages with the official streamlit AppTest API.

Run from the repo root:  .venv/bin/python ui/smoke_test.py

Uses wrapper scripts (instead of AppTest.from_function) because the pages
live in modules whose top-level imports (sys.path setup, `import streamlit`)
must execute — from_function copies only the function body.
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from streamlit.testing.v1 import AppTest

from ui import page_run, page_runs, page_tools, runner


def run_page_module(mod_name: str):
    """Render a ui.page_* module inside a proper AppTest script run."""
    src = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        f"from ui import {mod_name}\n"
        f"{mod_name}.render()\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        path = f.name
    at = AppTest.from_file(path, default_timeout=180)
    at.run()
    Path(path).unlink()
    return at


def main() -> int:
    failures = 0

    # --- app entry: navigation must execute the selected page ---------------
    at = AppTest.from_file(str(REPO_ROOT / "ui" / "app.py"), default_timeout=120)
    at.run()
    if at.exception:
        failures += 1
        print("  app.py: EXCEPTION")
        for e in at.exception:
            print("   ", getattr(e, "value", e), flush=True)
    elif len(at.header) == 0:
        failures += 1
        print("  app.py: EMPTY main area (st.Page functions never ran — call pg.run()!)", flush=True)
    else:
        print(f"  app.py: default page rendered OK ({len(at.header)} headers)", flush=True)

    # --- job runner: start a real pipeline job on the lightweight corpus ---
    if runner.status()["state"] == "running":
        print("a job is already running; aborting smoke test")
        return 1
    job = runner.start_job(
        "samples/lightweight_pdf_corpus/pdfs", "/tmp/glossapi_ui_smoke", "safe",
        fix_headings=True,
    )
    print(f"started test job {job['id']} (pid {job['pid']})", flush=True)
    deadline = time.time() + 300
    while time.time() < deadline:
        s = runner.status()
        if s["state"] != "running":
            break
        time.sleep(2)
    print(f"job finished in state: {s['state']}", flush=True)
    if s["state"] != "done":
        print(s.get("log", "")[-1000:])
        failures += 1
    elif "fix_headings:" not in s.get("log", ""):
        print("log is missing the 'fix_headings:' stage marker", flush=True)
        failures += 1
    runner.clear_finished_job()

    # --- fix_headings module: dry-run then apply on a synthetic file --------
    from fix_headings import fix_file

    demo = Path("/tmp/fh_demo")
    demo.mkdir(parents=True, exist_ok=True)
    f = demo / "t.md"
    f.write_text(
        "**ΜΕΓΑΛΟ ΚΕΦΑΛΑΙΟ**\n\nbody text\n\n"
        "**Heading words.** rest of the line\n"
        "**μοῖρα**: short glossary entry must stay\n",
        encoding="utf-8",
    )
    n_dry = fix_file(f, apply=False, verbose=False)
    n_app = fix_file(f, apply=True, verbose=False)
    content = f.read_text(encoding="utf-8")
    fh_ok = (
        n_dry == 2 and n_app == 2
        and content.startswith("## ΜΕΓΑΛΟ ΚΕΦΑΛΑΙΟ")
        and "## Heading words.\nrest of the line" in content
        and "**μοῖρα**" in content  # glossary-style entry untouched
    )
    print(f"fix_headings module: dry={n_dry}, apply={n_app}, ok={fh_ok}", flush=True)
    if not fh_ok:
        print(content, flush=True)
        failures += 1
    shutil.rmtree(demo, ignore_errors=True)

    code, out = runner.run_tool(["fix_headings.py", "pdf_in"])
    print(f"run_tool(fix_headings dry-run): code={code}, {len(out)} chars", flush=True)
    if code != 0:
        failures += 1

    # --- knowledge base: fresh build, then merge the same run again ----------
    run_dirs = sorted(Path("/tmp/glossapi_ui_smoke").glob("run_*"))
    kb = Path("/tmp/glossapi_ui_kb")
    if run_dirs:
        code_f, out_f = runner.run_tool(
            ["sections_to_obsidian.py", str(run_dirs[-1]), str(kb), "--fresh"])
        code_m, out_m = runner.run_tool(
            ["sections_to_obsidian.py", str(run_dirs[-1]), str(kb)])
        index_p = kb / "index.md"
        kb_ok = (
            code_f == 0 and code_m == 0 and index_p.exists()
            and "documents in the knowledge base" in index_p.read_text(encoding="utf-8")
        )
        print(f"vault fresh code={code_f}, merge code={code_m}, index ok={kb_ok}", flush=True)
        if not kb_ok:
            print(out_f[-500:], flush=True)
            print(out_m[-500:], flush=True)
            failures += 1
        shutil.rmtree(kb, ignore_errors=True)

        # combined export.jsonl over the smoke run's artifacts root
        from ui import page_tools

        count, runs, out = page_tools.build_combined_jsonl(Path("/tmp/glossapi_ui_smoke"))
        print(f"combined jsonl: {count} record(s) from {runs} run(s) -> {out}", flush=True)
        if count <= 0:
            failures += 1
        shutil.rmtree("/tmp/glossapi_ui_smoke", ignore_errors=True)
    else:
        print("no run dir found for vault merge test", flush=True)
        failures += 1

    # --- pages -------------------------------------------------------------
    for name, mod in [
        ("Run pipeline", "page_run"),
        ("Runs browser", "page_runs"),
        ("Tools", "page_tools"),
    ]:
        at = run_page_module(mod)
        exc = at.exception
        if exc:
            failures += 1
            print(f"  {name}: EXCEPTION", flush=True)
            for e in exc:
                print("   ", getattr(e, "value", e), flush=True)
        else:
            print(f"  {name}: rendered OK ({len(at.header)} headers)", flush=True)

    print("SMOKE TEST", "FAILED" if failures else "PASSED", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
