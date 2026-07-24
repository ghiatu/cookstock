#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_checkpoint.py

Resumable-scan checkpointing, borrowed from the design used by
github.com/RyanJHamby/stock-screener (their --resume / Git-based cache
strategy): persist progress to a JSON file INSIDE the repo (so it
survives between separate GitHub Actions job runs, which each get a
fresh, ephemeral filesystem) and skip tickers already handled today.

This does NOT make Yahoo Finance stop rate-limiting/blocking us - only a
proxy or a dedicated-IP runner can fix that at the root. What it does is
make a blocked/interrupted run non-destructive: whatever was already
scanned today is kept, and the next run (a manual re-run, which gets a
brand new GitHub-hosted runner with a different IP, or tomorrow's
scheduled run) only scans what's left.

File format (results/thai_scan_checkpoint.json):
{
    "date": "2026-07-24",
    "done_tickers": ["PTT.BK", "AOT.BK", ...],
    "passed": [{"PTT.BK": {...}}, ...]
}
"""
import os
import json
import datetime as dt


def _checkpoint_path(results_dir):
    return os.path.join(results_dir, 'thai_scan_checkpoint.json')


def load(results_dir):
    """Return (done_tickers: set, passed: list) for TODAY's date.
    If the checkpoint is from a previous day (or doesn't exist), start
    fresh - we want current data every trading day, not stale skips."""
    path = _checkpoint_path(results_dir)
    today = dt.date.today().isoformat()

    if not os.path.exists(path):
        return set(), []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[scan_checkpoint] couldn't read {path} ({exc}), starting fresh")
        return set(), []

    if data.get('date') != today:
        print(f"[scan_checkpoint] checkpoint is from {data.get('date')}, "
              f"not today ({today}) - starting a fresh scan")
        return set(), []

    done = set(data.get('done_tickers', []))
    passed = data.get('passed', [])
    print(f"[scan_checkpoint] resuming today's scan: {len(done)} tickers "
          f"already done, {len(passed)} passed so far")
    return done, passed


def save(results_dir, done_tickers, passed):
    """Overwrite today's checkpoint with the current progress."""
    os.makedirs(results_dir, exist_ok=True)
    path = _checkpoint_path(results_dir)
    data = {
        'date': dt.date.today().isoformat(),
        'updated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'done_tickers': sorted(done_tickers),
        'passed': passed,
    }
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)  # atomic write, avoids a half-written file


def clear(results_dir):
    """Remove today's checkpoint (e.g. after a fully successful scan, if
    you don't want it lingering) - optional, safe to skip since `load()`
    already ignores stale/yesterday's checkpoints automatically."""
    path = _checkpoint_path(results_dir)
    if os.path.exists(path):
        os.remove(path)
