#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_thai_tickers.py
Loads the list of Thai (SET + mai) stock symbols to scan, and converts
them into Yahoo Finance format (adds the ".BK" suffix Yahoo requires for
Stock Exchange of Thailand listings).

The symbol list itself lives in <repo_root>/data/thai_tickers.csv (one
symbol per line, no suffix, e.g. PTT / AOT / CPALL). Build/refresh it
with tools/build_thai_tickers.py from SET's official company list export.

NOTE ON DESIGN: this module used to derive the repo root itself with its
own find_path() (duplicating the logic in cookStockPipeline_thai.py).
That duplication kept drifting out of sync and re-breaking in slightly
different ways. Now the caller (the pipeline, which reliably resolves
the correct path every run) passes `repo_root` in directly - one source
of truth instead of two independent, occasionally-stale implementations.
"""
import os
import csv

# Used only as a safety-net if data/thai_tickers.csv is missing or the
# repo root can't be determined, so the pipeline never crashes with an
# empty ticker list. These are large, long-listed SET blue chips. For a
# real "scan all SET+mai" run, build data/thai_tickers.csv with
# tools/build_thai_tickers.py.
_FALLBACK_TICKERS = [
    'PTT', 'AOT', 'CPALL', 'ADVANC', 'SCB', 'KBANK', 'BBL', 'CPN', 'DELTA', 'GULF'
]


def get_thai_tickers(repo_root=None, csv_filename='data/thai_tickers.csv'):
    """
    repo_root: absolute path to the cookstock repo root (the folder that
    contains 'src/', 'batch/', 'data/'). Pass this in explicitly - see
    the NOTE above for why. If omitted, falls back to the small hardcoded
    list rather than guessing at a path (guessing is exactly what kept
    breaking).
    """
    if not repo_root:
        print("WARNING: get_thai_tickers() called without repo_root - "
              "using small fallback ticker list.")
        tickers = _FALLBACK_TICKERS
        return [t if t.endswith('.BK') else f"{t}.BK" for t in tickers]

    csv_path = os.path.join(repo_root, csv_filename)
    tickers = []

    if os.path.exists(csv_path):
        seen = set()
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                symbol = row[0].strip().upper()
                if not symbol or symbol == 'SYMBOL' or symbol.startswith('#'):
                    continue
                if symbol in seen:
                    continue
                seen.add(symbol)
                tickers.append(symbol)

        if len(tickers) < 100:
            print(f"WARNING: only {len(tickers)} tickers loaded from {csv_path} - "
                  f"that's far short of the ~850 SET+mai listed companies. "
                  f"Did you mean to run tools/build_thai_tickers.py to refresh the full list?")
    else:
        print(f"WARNING: {csv_path} not found, using small fallback ticker list.")
        tickers = _FALLBACK_TICKERS

    # Yahoo Finance needs the .BK suffix for SET-listed stocks
    yahoo_tickers = [t if t.endswith('.BK') else f"{t}.BK" for t in tickers]
    return yahoo_tickers


if __name__ == '__main__':
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    tks = get_thai_tickers(repo_root=root)
    print(f"Loaded {len(tks)} Thai tickers")
    print(tks[:10])
