#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_thai_tickers.py
Loads the list of Thai (SET) stock symbols to scan, and converts them into
Yahoo Finance format (adds the ".BK" suffix that Yahoo Finance requires for
stocks listed on the Stock Exchange of Thailand).

The symbol list itself lives in data/thai_tickers.csv (one symbol per line,
no suffix, e.g. PTT / AOT / CPALL). See README_THAI.md for how to build a
full-market list from SET's official "Listed Company" download.
"""
import os
import csv


def find_path():
    home_dir = os.path.expanduser("~")
    for root, dirs, files in os.walk(home_dir):
        if 'cookstock' in dirs:
            return os.path.join(root, 'cookstock')
    return None


# Used only as a safety-net if data/thai_tickers.csv is missing, so the
# pipeline never crashes with an empty ticker list. These are large,
# long-listed SET blue chips. For a real "scan all SET stocks" run, build
# data/thai_tickers.csv as described in README_THAI.md.
_FALLBACK_TICKERS = [
    'PTT', 'AOT', 'CPALL', 'ADVANC', 'SCB', 'KBANK', 'BBL', 'CPN', 'DELTA', 'GULF'
]


def get_thai_tickers(csv_filename='data/thai_tickers.csv'):
    basePath = find_path()
    csv_path = os.path.join(basePath, csv_filename)
    tickers = []

    if os.path.exists(csv_path):
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                symbol = row[0].strip().upper()
                if not symbol or symbol == 'SYMBOL':
                    continue
                tickers.append(symbol)
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
