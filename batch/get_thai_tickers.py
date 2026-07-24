#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_thai_tickers.py
Loads the list of Thai (SET + mai) stock symbols to scan, and converts
them into Yahoo Finance format (adds the ".BK" suffix Yahoo requires for
Stock Exchange of Thailand listings).

The symbol list itself lives in data/thai_tickers.csv (one symbol per
line, no suffix, e.g. PTT / AOT / CPALL). Build/refresh it with
tools/build_thai_tickers.py from SET's official company list export.
"""
import os
import csv


def find_path():
    """
    Locate the cookstock repo root (the folder containing 'data/').

    1) On GitHub Actions, GITHUB_WORKSPACE always points at the correct
       checkout root. We prefer this because actions/checkout clones the
       repo into .../work/<repo>/<repo>/, i.e. TWO nested folders both
       named 'cookstock' - a naive os.walk() search finds the OUTER one
       first (which has no real repo contents inside it), and using that
       silently breaks every path built from it.
    2) Otherwise, derive the repo root from this script's own location
       (this script lives in <repo>/batch/), which is robust regardless
       of what the surrounding folders are named.
    3) Last resort: walk the home directory, but verify the candidate
       actually looks like the repo root (has a 'src' dir - 'data' may
       not exist yet on a fresh checkout before thai_tickers.csv exists)
       before accepting it.
    """
    ws = os.environ.get('GITHUB_WORKSPACE')
    if ws and os.path.isdir(os.path.join(ws, 'src')):
        return ws

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = script_dir
    for _ in range(4):
        if os.path.basename(candidate) == 'cookstock' and os.path.isdir(os.path.join(candidate, 'src')):
            return candidate
        candidate = os.path.dirname(candidate)

    home_dir = os.path.expanduser("~")
    for root, dirs, files in os.walk(home_dir):
        if 'cookstock' in dirs:
            cand = os.path.join(root, 'cookstock')
            if os.path.isdir(os.path.join(cand, 'src')):
                return cand
    return None


# Used only as a safety-net if data/thai_tickers.csv is missing, so the
# pipeline never crashes with an empty ticker list. These are large,
# long-listed SET blue chips. For a real "scan all SET+mai" run, build
# data/thai_tickers.csv with tools/build_thai_tickers.py.
_FALLBACK_TICKERS = [
    'PTT', 'AOT', 'CPALL', 'ADVANC', 'SCB', 'KBANK', 'BBL', 'CPN', 'DELTA', 'GULF'
]


def get_thai_tickers(csv_filename='data/thai_tickers.csv'):
    basePath = find_path()
    if basePath is None:
        print("WARNING: could not locate the cookstock repo root at all, "
              "using small fallback ticker list.")
        tickers = _FALLBACK_TICKERS
        return [t if t.endswith('.BK') else f"{t}.BK" for t in tickers]

    csv_path = os.path.join(basePath, csv_filename)
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
    tks = get_thai_tickers()
    print(f"Loaded {len(tks)} Thai tickers")
    print(tks[:10])
