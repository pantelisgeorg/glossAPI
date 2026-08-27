#!/usr/bin/env python
"""Inspect glossAPI parquet artifacts.

Usage:
  view_parquets.py                          list all tables under artifacts/
  view_parquets.py PATH                     PATH = dir -> list, parquet -> show
  view_parquets.py FILE --cols a,b,c        show only these columns
  view_parquets.py FILE --rows N            how many rows (default 20)
  view_parquets.py FILE --all               include long text/JSON columns
  view_parquets.py FILE --csv out.csv       export the full table to CSV
  view_parquets.py FILE --dump ROWID --col section   print one cell in full
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

LONG_CELL = 60  # cells longer than this are truncated in the default view
MAX_DEFAULT_ROWS = 20


def find_parquets(root: Path):
    return [
        p
        for p in sorted(root.rglob("*.parquet"))
        if not any(".tmp" in part for part in p.parts)
    ]


def list_tables(root: Path) -> None:
    parquets = find_parquets(root)
    if not parquets:
        print(f"No parquet files found under {root}")
        return
    print(f"{len(parquets)} table(s) under {root}:")
    for p in parquets:
        df = pd.read_parquet(p)
        print(f"  {len(df.columns):>3} cols  {len(df):>6} rows  {p}")


def short_columns(df: pd.DataFrame, limit: int = LONG_CELL):
    cols = []
    for col in df.columns:
        s = df[col].dropna().astype(str)
        if s.empty:
            cols.append(col)
            continue
        if s.str.len().mean() <= limit:
            cols.append(col)
    return cols


def show_table(path: Path, args) -> None:
    df = pd.read_parquet(path)
    if args.cols:
        missing = [c for c in args.cols if c not in df.columns]
        if missing:
            print(f"Columns not found: {missing}\nAvailable: {list(df.columns)}")
            sys.exit(1)
        cols = args.cols
    elif args.all:
        cols = list(df.columns)
    else:
        cols = short_columns(df)
        hidden = [c for c in df.columns if c not in cols]
    view = df[cols].head(args.rows)
    if not args.all:
        view = view.map(
            lambda v: (v[:LONG_CELL] + "...") if isinstance(v, str) and len(v) > LONG_CELL else v
        )
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 250)
    print(f"{path}  ->  {df.shape[0]} rows x {df.shape[1]} cols")
    if not args.all and hidden:
        print(f"hidden long columns: {', '.join(hidden)}  (use --all or --cols)")
    print("-" * 100)
    print(view.to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect glossAPI parquet artifacts.")
    ap.add_argument("path", nargs="?", default="artifacts")
    ap.add_argument("--cols", help="comma-separated columns to show")
    ap.add_argument("--rows", type=int, default=MAX_DEFAULT_ROWS)
    ap.add_argument("--all", action="store_true", help="show long text/JSON columns")
    ap.add_argument("--csv", help="export full table to CSV")
    ap.add_argument("--dump", help="row id to print in full")
    ap.add_argument("--col", default="section", help="column for --dump")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Not found: {path}")
        sys.exit(1)
    if path.is_dir():
        list_tables(path)
        return

    if args.csv:
        pd.read_parquet(path).to_csv(args.csv, index=False)
        print(f"Exported {path} -> {args.csv}")
        return
    if args.dump:
        df = pd.read_parquet(path)
        rows = df[df["id"].astype(str) == str(args.dump)]
        if rows.empty and args.dump in df["filename"].astype(str).values:
            rows = df[df["filename"] == args.dump]
        if rows.empty:
            print(f"No row with id/filename '{args.dump}'")
            sys.exit(1)
        for val in rows[args.col]:
            print(val)
        return

    args.cols = [c.strip() for c in args.cols.split(",")] if args.cols else None
    show_table(path, args)


if __name__ == "__main__":
    main()
