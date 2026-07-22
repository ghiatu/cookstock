#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cookStockPipeline_thai.py
Thai (SET) version of the cookstock batch pipeline.

1. Loads Thai ticker list (data/thai_tickers.csv, via get_thai_tickers.py)
2. Runs Minervini Stage-2 + Volatility Contraction Pattern screening
   (batch_pipeline_full from cookStock.py) on every ticker
3. Sends a text summary + chart images to Telegram
"""
import os
import sys
import glob
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

import matplotlib
matplotlib.use('Agg')  # headless runner - no display available

import cookStock
from cookStock import *  # noqa: F401,F403  (brings in batch_process, cookFinancials, etc.)

from get_thai_tickers import get_thai_tickers
import telegram_notify

current_date = dt.date.today().strftime("%Y-%m-%d")
sectorNameStr = "THAI_ALL"

selected = get_thai_tickers()
print(f"Scanning {len(selected)} Thai tickers...")

y = batch_process(selected, sectorNameStr)
y.batch_pipeline_full()

# ---------------- build & send Telegram summary ----------------
result_path = os.path.join(y.resultsPath, sectorNameStr + '.json')
with open(result_path, 'r') as f:
    result_data = js.load(f)['data']

passed = [d for d in result_data if isinstance(d, dict)]

lines = [
    f"<b>Cookstock (Thai/SET) - {current_date}</b>",
    f"Scanned: {len(selected)} tickers",
    f"Passed VCP screen: {len(passed)}",
    "",
]

for item in passed:
    for ticker, info in item.items():
        lines.append(
            f"- <b>{ticker}</b> price {info.get('current price')} | "
            f"pivot ok: {info.get('is_good_pivot')} | "
            f"deep correction: {info.get('is_deep_correction')} | "
            f"demand dry: {info.get('is_demand_dry')}"
        )

summary_text = "\n".join(lines) if passed else (
    f"<b>Cookstock (Thai/SET) - {current_date}</b>\n"
    f"Scanned: {len(selected)} tickers\n"
    f"No stocks passed the VCP screen today."
)

telegram_notify.send_text(summary_text)

# send charts for stocks that saved a .jpg (passed pivot + correction + demand-dry checks)
chart_files = sorted(glob.glob(os.path.join(y.resultsPath, '*.jpg')))
for chart in chart_files:
    ticker_name = os.path.splitext(os.path.basename(chart))[0]
    telegram_notify.send_photo(chart, caption=ticker_name)

print(f"Done. Sent {len(chart_files)} charts to Telegram.")
