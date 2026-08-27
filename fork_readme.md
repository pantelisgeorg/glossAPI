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
| `fix_headings.py` | Convert full-line `**bold**` (and `*italic*` with `--italic`) headings to `##` so the sectioner splits documents properly. Dry-run by default; add `--apply` to write. |
| `sections_to_obsidian.py` | Convert a run's sections into a self-contained Obsidian vault (`vault/`): `index.md` + one note per document + one note per section, with pipeline metadata (quality scores, `predicted_section`, page `place`) in YAML frontmatter and wikilinks. Anyone can open it — no local setup needed. |

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

## Notes
- GPU torch is verified (`2.5.1+cu121`, CUDA available). A bare `-e .` install
  may resolve a newer cu1xx torch; install `.[cuda]` for the exact pinned build.
- `annotate()` still warns "No document type information available" unless you
  pass a `metadata_path` parquet with `filename` + `document_type` columns —
  classification itself runs fine without it.
- Upstream PRs target their `development` branch; this fork pushes to `master`
  and is not intended to be merged back as-is.
