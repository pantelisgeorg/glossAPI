#!/usr/bin/env python
"""Print every parquet under artifacts/ (or a given dir) with pandas.

Long text cells are truncated so the terminal stays readable.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
MAX_ROWS = 20
MAX_CELL = 120

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


def truncate(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(
                lambda v: v[:MAX_CELL] + "..." if isinstance(v, str) and len(v) > MAX_CELL else v
            )
    return df


parquets = [
    p
    for p in sorted(ROOT.rglob("*.parquet"))
    if not any(".tmp" in part for part in p.parts)
]
if not parquets:
    print(f"No parquet files found under {ROOT}")
    sys.exit(1)

for p in parquets:
    df = truncate(pd.read_parquet(p))
    print("=" * 100)
    print(f"{p}  ->  {df.shape[0]} rows x {df.shape[1]} cols")
    print("-" * 100)
    print(df.head(MAX_ROWS).to_string(index=False))
    print()
