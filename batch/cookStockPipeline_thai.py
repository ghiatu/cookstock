#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cookStockPipeline_thai.py
Thai (SET + mai) version of the cookstock batch pipeline.

1. Loads the full Thai ticker list (data/thai_tickers.csv, via
   get_thai_tickers.py) - build that CSV with tools/build_thai_tickers.py
2. Runs Minervini Stage-2 + Volatility Contraction Pattern screening
   (batch_pipeline_full from cookStock.py) on every ticker, in chunks,
   with HTTP-level pacing/retry (yahoo_rate_limiter.py) so a full-market
   scan (~800+ symbols) doesn't get flagged as bot traffic by Yahoo
3. Sends a text summary + chart images to Telegram, including how the
   scan went (retries, tickers that errored out, etc.)
"""
import os
import sys
import glob
import time
import random
import datetime as dt
import json as js


def find_path():
    """
    Locate the cookstock repo root (the folder containing 'src/').

    1) On GitHub Actions, GITHUB_WORKSPACE always points at the correct
       checkout root. We prefer this because actions/checkout clones the
       repo into .../work/<repo>/<repo>/, i.e. TWO nested folders both
       named 'cookstock' - a naive os.walk() search finds the OUTER one
       first (which has no 'src/' inside) and returns the wrong path.
    2) Otherwise, derive the repo root from this script's own location
       (this script lives in <repo>/batch/), which is robust regardless
       of what the surrounding folders are named.
    3) Last resort: walk the home directory, but verify 'src/' actually
       exists before accepting a candidate.
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


basePath = find_path()
srcPath = os.path.join(basePath, 'src')
sys.path.insert(0, srcPath)

# IMPORTANT: this patches `requests` so every HTTP call yahoofinancials
# makes gets paced + retried. Must be imported BEFORE `import cookStock`.
import yahoo_rate_limiter  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use('Agg')  # headless runner - no display available

import cookStock  # noqa: E402
from cookStock import *  # noqa: F401,F403,E402  (brings in batch_process, cookFinancials, etc.)

from get_thai_tickers import get_thai_tickers  # noqa: E402
import telegram_notify  # noqa: E402

current_date = dt.date.today().strftime("%Y-%m-%d")
sectorNameStr = "THAI_ALL"

# ---- scan tuning (all overridable via workflow env / repo secrets) ----
CHUNK_SIZE = int(os.environ.get('THAI_SCAN_CHUNK_SIZE', '40'))
CHUNK_PAUSE_MIN = float(os.environ.get('THAI_SCAN_CHUNK_PAUSE_MIN_SEC', '20'))
CHUNK_PAUSE_MAX = float(os.environ.get('THAI_SCAN_CHUNK_PAUSE_MAX_SEC', '45'))

selected = get_thai_tickers()
print(f"Scanning {len(selected)} Thai tickers (SET + mai) in chunks of {CHUNK_SIZE}...")

chunks = [selected[i:i + CHUNK_SIZE] for i in range(0, len(selected), CHUNK_SIZE)]

all_passed = []
failed_tickers = []
y = None  # keep a reference to the last batch_process instance (for resultsPath)

for idx, chunk in enumerate(chunks, start=1):
    print(f"--- Chunk {idx}/{len(chunks)} ({len(chunk)} tickers) ---")
    chunk_label = f"{sectorNameStr}_chunk{idx:03d}"
    try:
        y = batch_process(chunk, chunk_label)
        y.batch_pipeline_full()

        result_path = os.path.join(y.resultsPath, chunk_label + '.json')
        with open(result_path, 'r') as f:
            chunk_data = js.load(f)['data']
        all_passed.extend([d for d in chunk_data if isinstance(d, dict)])

    except Exception as exc:
        # One bad chunk (e.g. persistent 429s) should not kill the whole
        # scan - log it, keep going, and report it in the Telegram summary.
        print(f"!!! Chunk {idx} failed: {exc}")
        failed_tickers.extend(chunk)

    # pause *between* chunks on top of the per-request pacing already
    # applied inside yahoo_rate_limiter - extra breathing room for Yahoo
    if idx < len(chunks):
        pause = random.uniform(CHUNK_PAUSE_MIN, CHUNK_PAUSE_MAX)
        print(f"Pausing {pause:.0f}s before next chunk...")
        time.sleep(pause)

passed = all_passed

# ---------------- build & send Telegram summary ----------------
rl_stats = yahoo_rate_limiter.stats
lines = [
    f"<b>Cookstock (Thai SET+mai) - {current_date}</b>",
    f"Scanned: {len(selected)} tickers ({len(chunks)} chunks)",
    f"Passed VCP screen: {len(passed)}",
]
if failed_tickers:
    lines.append(f"⚠️ Failed chunks: {len(failed_tickers)} tickers could not be scanned")
if rl_stats['retries'] or rl_stats['blocked_giveups']:
    lines.append(
        f"HTTP retries: {rl_stats['retries']} | "
        f"gave up after max retries: {rl_stats['blocked_giveups']}"
    )
lines.append("")

for item in passed:
    for ticker, info in item.items():
        lines.append(
            f"- <b>{ticker}</b> price {info.get('current price')} | "
            f"pivot ok: {info.get('is_good_pivot')} | "
            f"deep correction: {info.get('is_deep_correction')} | "
            f"demand dry: {info.get('is_demand_dry')}"
        )

summary_text = "\n".join(lines) if passed else "\n".join(lines + ["No stocks passed the VCP screen today."])

telegram_notify.send_text(summary_text)

# send charts for stocks that saved a .jpg (passed pivot + correction + demand-dry checks)
if y is not None:
    chart_files = sorted(glob.glob(os.path.join(y.resultsPath, '*.jpg')))
    for chart in chart_files:
        ticker_name = os.path.splitext(os.path.basename(chart))[0]
        telegram_notify.send_photo(chart, caption=ticker_name)
    print(f"Done. Sent {len(chart_files)} charts to Telegram.")
else:
    print("Done. No successful chunks, no charts to send.")

print(f"Request stats: {rl_stats}")
if failed_tickers:
    print(f"Tickers in failed chunks ({len(failed_tickers)}): {failed_tickers}")

