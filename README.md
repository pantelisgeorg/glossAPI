# GlossAPI — fork notes

This is a fork of [eellak/glossAPI](https://github.com/eellak/glossAPI) (EUPL-1.2,
license unchanged) with fixes and helper tools so that a fresh clone works
end-to-end without manual steps.

## What this fork changes vs upstream

### 1. Install fixes
- **Docling is now a core dependency** (`pyproject.toml`). Upstream lists it as
  optional, but `gloss_extract.py` hard-imports it even for the "safe" backend,
  so a bare `pip install -e .` crashed with `ModuleNotFoundError: docling`.
- **`requires-python = ">=3.9,<3.13"`** — the pinned CUDA torch/torchvision
  wheels (cu121) have no cp313 wheels; Python 3.13 installs fail.
- **`[tool.uv]` index/sources for cu121** — `uv` installs get GPU torch builds
  instead of PyPI CPU wheels (docling-ibm-models pulls torch transitively).
- **Extras:** `.[cuda]` (pinned `torch==2.5.1`, `torchvision==0.20.1`),
  `.[rapidocr]` (GPU OCR stack), `.[test]` (pytest + fpdf2).
- **Rust extensions self-heal.** `Corpus.clean()` auto-builds
  `glossapi_rs_cleaner` / `glossapi_rs_noise` via maturin if they are missing.
  Fixed two upstream bugs in that fallback:
  - works in uv-managed venvs (no `pip` module): installs maturin via `uv pip
    install --python <venv>` as fallback,
  - `maturin develop` gets `VIRTUAL_ENV` set, otherwise it installs into the
    venv detected from the current directory (the wrong one in many cases).

### 2. Pretrained models shipped in the repo
`src/glossapi/corpus/models/section_classifier.joblib` and
`kmeans_weights.joblib` (extracted from the upstream PyPI wheel). This makes
`Corpus.annotate()` work out of the box; upstream's git checkout ships neither
model and silently skips annotation.

### 3. Metadata filename fix
Two places hardcoded `filename = <stem>.pdf` when merging cleaner/noise
metrics. Markdown/docx/etc. inputs now keep their true name and extension
(e.g. `13.Plato's Republic.md`, `file_ext=md`) and no phantom `.pdf` row is
created. (See commit `df8a71f`.)

### 4. Docs
README and `docs/getting_started.md` updated: docling as core dep, Python
3.9–3.12 requirement, uv variant, `.[cuda]` pinned-vs-latest explanation.

## Helper tools added by this fork

| File | What it does |
| --- | --- |
| `run.sh` | One-command pipeline: drop files in `pdf_in/`, run `./run.sh`, get `extract → clean → section → annotate → jsonl`. Auto-selects the Docling backend for non-PDF inputs. Each run writes to its own folder (`artifacts/<file-stem>/` or `artifacts/run_<timestamp>/`). |
| `view_parquets.py` | Inspect pipeline parquets: table listing, `--cols a,b,c`, `--all` (long text columns), `--dump <id> --col <col>` (print one cell in full), `--csv out.csv`. |
| `parquets_to_db.py` | Import all parquets into one DuckDB file (`artifacts/glossapi.duckdb`) that you can open in DBeaver / TablePlus / DB Browser. |
| `fix_headings.py` | Convert full-line `**bold**` (and `*italic*` with `--italic`) headings to `##` so the sectioner splits documents properly. Dry-run by default; add `--apply` to write. Also importable (`fix_file`) — the UI's optional *fix headings after extraction* step uses it on generated `clean_markdown/` between clean and section, which is how PDFs (which only become markdown during extraction) get heading repair before sectioning. |
| `sections_to_obsidian.py` | Maintain a **persistent Obsidian vault / knowledge base** (`vault/`): each run is merged in — new documents added, same-name documents updated in place, `index.md` rebuilt from the whole vault; other documents untouched. `--fresh` wipes the vault first. Notes carry pipeline metadata (quality scores, `predicted_section`, page `place`) in YAML frontmatter and wikilinks; section headings appear **in full** in note titles and link aliases — only the note *filename* is truncated to 80 chars for filesystem safety. |

## Quick start

```bash
git clone https://github.com/pantelisgeorg/glossAPI.git
cd glossAPI
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e .            # core (docling + torch from cu121 index, GPU build)
# optional: uv pip install -e ".[cuda,rapidocr,test]"
mkdir pdf_in                  # put PDFs / .md / .docx / .html here
./run.sh                      # full pipeline -> artifacts/<name>/
```

Then explore the results:

```bash
.venv/bin/python view_parquets.py artifacts/<name>          # or no args to list all
.venv/bin/python parquets_to_db.py                          # -> artifacts/glossapi.duckdb for DBeaver
.venv/bin/python fix_headings.py pdf_in                     # dry-run heading fixes
```

## Web UI (Streamlit)

The fork also ships a local single-user web UI that wraps the pipeline, the
run browser, and the helper scripts — no CLI needed:

```bash
uv pip install -e ".[ui]"     # adds streamlit
streamlit run ui/app.py       # opens http://localhost:8501
```

Pages:

| Page | What it does |
| --- | --- |
| **Run pipeline** | Upload files into `pdf_in/` (or use what's there), pick the backend (`auto`/`safe`/`docling`), optionally tick **"Fix bold headings after extraction"** (applies `fix_headings` to the generated markdown between clean and section — the right moment for PDFs), start the run and watch its live log. Jobs run as a background subprocess, so the browser never blocks; one job at a time, with cancel support. |
| **Runs browser** | Explore any `artifacts/<run>/`: per-file metrics, every parquet table (click a row to read the full section text), raw vs cleaned markdown side-by-side, and download buttons for `export.jsonl` or any table as CSV. |
| **Tools** | `fix_headings.py` (dry-run / confirmed `--apply`), `parquets_to_db.py` (build + download `glossapi.duckdb`), `sections_to_obsidian.py` (add a run to the vault **knowledge base** — merge is the default — or rebuild it from scratch; download as zip), and a **combined export.jsonl** builder that concatenates every run's export into one cumulative training file. |

Implementation lives in `ui/` (`app.py` + `pipeline_main.py` + `runner.py` +
page modules). The pipeline subprocess runs the same code as `run.sh`
(`ui/pipeline_main.py`), and job state is kept under `artifacts/.ui_jobs/`.
The helper scripts themselves are unchanged — the UI just calls them and
captures their output.

**Precaution — combined export.jsonl:** `artifacts/export_all.jsonl` is a
straight concatenation of every run's `export.jsonl`. If the *same file* is
processed in more than one run (e.g. re-run after a fix), its records will
appear once per run in the combined file — the vault merge dedupes by document
name, the JSONL does not. Regenerate the combined file after cleaning up
duplicate runs if exact one-record-per-section matters for training data.

## Notes
- A local `sessions/` folder (gitignored) keeps chat-session exports and a small
  `export_cline_session.py` helper that turns a completed Cline task's
  `api_conversation_history.json` into a readable Markdown transcript.
- GPU torch is verified (`2.5.1+cu121`, CUDA available). A bare `-e .` install
  may resolve a newer cu1xx torch; install `.[cuda]` for the exact pinned build.
- `annotate()` still warns "No document type information available" unless you
  pass a `metadata_path` parquet with `filename` + `document_type` columns —
  classification itself runs fine without it.
- Upstream PRs target their `development` branch; this fork pushes to `master`
  and is not intended to be merged back as-is.
