#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cookStockPipeline_thai.py
Thai (SET + mai) version of the cookstock batch pipeline.

1. Loads the full Thai ticker list (data/thai_tickers.csv, via
   get_thai_tickers.py) - build that CSV with tools/build_thai_tickers.py
2. Runs Minervini Stage-2 + Volatility Contraction Pattern screening
   (batch_pipeline_full from cookStock.py) on every ticker not already
   done today, in chunks, with HTTP-level pacing/retry
   (yahoo_rate_limiter.py) and RESUMABLE CHECKPOINTING
   (scan_checkpoint.py) - a design borrowed from
   github.com/RyanJHamby/stock-screener's Git-based cache/--resume
   strategy: if Yahoo blocks us partway through, whatever was already
   scanned today is preserved, and the NEXT run (manual re-run = a fresh
   GitHub-hosted runner with a different IP, or tomorrow's cron) only
   scans what's left instead of starting over.
3. Sends a text summary + chart images to Telegram, including how the
   scan went (retries, tickers left to resume, etc.)
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
import scan_checkpoint  # noqa: E402

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

all_tickers = get_thai_tickers()

# ---- resume from today's checkpoint, if any (results dir is fixed by
#      cookStock regardless of chunk label, so we can compute it before
#      the first batch_process instance exists) ----
resultsRoot = os.path.join(basePath, 'results')
done_tickers, all_passed = scan_checkpoint.load(resultsRoot)

selected = [t for t in all_tickers if t not in done_tickers]
print(f"Total universe: {len(all_tickers)} tickers (SET + mai). "
      f"Already done today: {len(done_tickers)}. Remaining: {len(selected)}.")

chunks = [selected[i:i + CHUNK_SIZE] for i in range(0, len(selected), CHUNK_SIZE)]

failed_tickers = []
y = None  # keep a reference to the last batch_process instance (for resultsPath)
blocked_abort = False

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
        done_tickers.update(chunk)

        # checkpoint after EVERY successful chunk, not just at the end -
        # this is what makes a mid-scan block non-destructive
        scan_checkpoint.save(resultsRoot, done_tickers, all_passed)

    except yahoo_rate_limiter.YahooBlockedError as exc:
        # Retrying more chunks would just repeat the same failure for
        # the rest of the market - stop now, keep what we already have
        # checkpointed, and report clearly instead of burning the job's
        # timeout on doomed requests.
        print(f"!!! Aborting scan early: {exc}")
        failed_tickers.extend(chunk)
        remaining = [t for c in chunks[idx:] for t in c]
        failed_tickers.extend(remaining)
        blocked_abort = True
        break

    except Exception as exc:
        # One bad chunk (e.g. a data/parsing error unrelated to blocking)
        # should not kill the whole scan - log it, keep going, and report
        # it in the Telegram summary. Don't mark these tickers as done,
        # so they'll be retried on the next run instead of skipped.
        print(f"!!! Chunk {idx} failed: {exc}")
        failed_tickers.extend(chunk)

    # pause *between* chunks on top of the per-request pacing already
    # applied inside yahoo_rate_limiter - extra breathing room for Yahoo
    if idx < len(chunks):
        pause = random.uniform(CHUNK_PAUSE_MIN, CHUNK_PAUSE_MAX)
        print(f"Pausing {pause:.0f}s before next chunk...")
        time.sleep(pause)

passed = all_passed
fully_complete = (not blocked_abort) and (not failed_tickers) and (len(done_tickers) >= len(all_tickers))

# ---------------- build & send Telegram summary ----------------
rl_stats = yahoo_rate_limiter.stats
lines = [
    f"<b>Cookstock (Thai SET+mai) - {current_date}</b>",
    f"Universe: {len(all_tickers)} tickers | Done today: {len(done_tickers)} | "
    f"This run scanned: {len(selected)}",
    f"Passed VCP screen (cumulative today): {len(passed)}",
]
if blocked_abort:
    lines.append(
        f"🚫 Scan stopped early: Yahoo Finance appears to be blocking this "
        f"runner's IP outright ({len(failed_tickers)} tickers not scanned yet). "
        f"Progress is saved - re-run the workflow (gets a fresh runner) to "
        f"continue, or set YF_PROXY_URL / use a self-hosted runner for a "
        f"permanent fix."
    )
elif failed_tickers:
    lines.append(f"⚠️ {len(failed_tickers)} tickers errored this run - "
                  f"will retry automatically on the next run")
elif fully_complete:
    lines.append("✅ Full market scan complete for today")
lines.append("")

for item in passed:
    for ticker, info in item.items():
        lines.append(
            f"- <b>{ticker}</b> price {info.get('current price')} | "
            f"pivot ok: {info.get('is_good_pivot')} | "
            f"deep correction: {info.get('is_deep_correction')} | "
            f"demand dry: {info.get('is_demand_dry')}"
        )

summary_text = "\n".join(lines) if passed else "\n".join(lines + ["No stocks passed the VCP screen today (so far)."])

telegram_notify.send_text(summary_text)

# send charts for stocks that saved a .jpg (passed pivot + correction + demand-dry checks)
if y is not None:
    chart_files = sorted(glob.glob(os.path.join(y.resultsPath, '*.jpg')))
    for chart in chart_files:
        ticker_name = os.path.splitext(os.path.basename(chart))[0]
        telegram_notify.send_photo(chart, caption=ticker_name)
    print(f"Done. Sent {len(chart_files)} charts to Telegram.")
else:
    print("Done. No successful chunks this run, no charts to send.")

print(f"Request stats: {rl_stats}")
if failed_tickers:
    print(f"Tickers not yet done ({len(failed_tickers)}): {failed_tickers}")

# Non-zero exit when blocked so the GitHub Actions run is visibly marked
# failed (easy to notice + can wire up auto-retry / alerting on this),
# while still having saved all progress via the checkpoint above.
if blocked_abort:
    sys.exit(1)


