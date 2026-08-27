#!/usr/bin/env python
"""Import all parquet tables under a folder into a single DuckDB database.

Usage:
  python parquets_to_db.py [FOLDER] [OUTPUT.duckdb]

Defaults: FOLDER=artifacts, OUTPUT=artifacts/glossapi.duckdb

Open the resulting file in any DuckDB-compatible viewer (DBeaver, TablePlus,
DB Browser) or query it with duckdb CLI / Python.
"""
import re
import sys
from pathlib import Path

import duckdb

FOLDER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else FOLDER / "glossapi.duckdb"

parquets = [
    p
    for p in sorted(FOLDER.rglob("*.parquet"))
    if not any(".tmp" in part for part in p.parts)
]
if not parquets:
    print(f"No parquet files found under {FOLDER}")
    sys.exit(1)

OUT.parent.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(OUT))
for p in parquets:
    table = re.sub(r"[^A-Za-z0-9_]+", "_", p.relative_to(FOLDER).with_suffix("").as_posix()).strip("_")
    if not table or table[0].isdigit():
        table = "t_" + table
    con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM read_parquet(?)', [str(p)])
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<40} {n:>6} rows  <- {p}")

con.close()
print(f"\nDone -> {OUT}")
print("Open it in DBeaver: New connection -> DuckDB -> select this file.")
