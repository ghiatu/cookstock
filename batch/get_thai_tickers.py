#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_thai_tickers.py
Loads the list of Thai stock symbols to scan, and converts them into
Yahoo Finance format (adds the ".BK" suffix Yahoo requires for Stock
Exchange of Thailand listings).

The symbol list itself lives in <repo_root>/data/thai_tickers.csv (one
symbol per line, no suffix, e.g. PTT / AOT / CPALL).

DESIGN NOTE (changed after a real incident): this used to silently fall
back to a hardcoded 10-stock list whenever the repo root or CSV couldn't
be found/read, so the pipeline would "never crash". In practice this
meant it could silently scan a completely different, unrelated set of
stocks (including tickers the user had deliberately REMOVED from their
list) without any visible error - very confusing. Silently substituting
data is worse than failing loudly. Now this raises TickerListError
instead: the pipeline catches it and sends a clear Telegram alert, so
you always know exactly which tickers were scanned, or that none were.
"""
import os
import csv


class TickerListError(Exception):
    """Raised when the real ticker list can't be loaded - the caller
    should stop and report this clearly rather than substituting a
    different, unrelated list of stocks silently."""
    pass


def get_thai_tickers(repo_root, csv_filename='data/thai_tickers.csv'):
    """
    repo_root: absolute path to the cookstock repo root (the folder that
    contains 'src/', 'batch/', 'data/'). The caller (the pipeline, which
    reliably resolves this every run) must pass it in explicitly.

    Raises TickerListError if repo_root is missing/falsy or the CSV
    doesn't exist/is empty - on purpose, so a broken path never results
    in silently scanning the wrong stocks. No hidden fallback list.
    """
    if not repo_root:
        raise TickerListError(
            "get_thai_tickers() was called without a repo_root - the "
            "pipeline couldn't determine where the repo is checked out."
        )

    csv_path = os.path.join(repo_root, csv_filename)

    if not os.path.exists(csv_path):
        raise TickerListError(f"Ticker list not found at {csv_path}")

    tickers = []
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

    if not tickers:
        raise TickerListError(f"{csv_path} exists but contains no valid tickers")

    print(f"[get_thai_tickers] loaded {len(tickers)} tickers from {csv_path}: {tickers}")

    # Yahoo Finance needs the .BK suffix for SET-listed stocks
    return [t if t.endswith('.BK') else f"{t}.BK" for t in tickers]


if __name__ == '__main__':
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    tks = get_thai_tickers(repo_root=root)
    print(f"Loaded {len(tks)} Thai tickers")
    print(tks)
