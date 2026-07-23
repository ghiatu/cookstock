#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yahoo_rate_limiter.py

Patches Python's `requests` library so EVERY outgoing HTTP call (made by
`yahoofinancials`, which cookStock.py uses under the hood) is:
  1. paced with a randomized delay, so ~800+ requests for a full SET+mai
     scan don't fire back-to-back like a script would,
  2. sent with a realistic browser User-Agent header,
  3. automatically retried with exponential backoff on HTTP 429 (rate
     limited) or 5xx responses, and on connection/timeout errors.

USAGE: import this module BEFORE `import cookStock` (or anything that
imports `yahoofinancials`). The patch is applied at import time and affects
every `requests.Session` used afterwards - including ones created deep
inside yahoofinancials that we never see directly.

    import yahoo_rate_limiter   # <- must come first
    import cookStock

Tunable via environment variables (all optional, sensible defaults below):
    YF_MIN_DELAY_SEC   min seconds between requests   (default 1.0)
    YF_MAX_DELAY_SEC   max seconds between requests   (default 2.2)
    YF_MAX_RETRIES     retries per request             (default 5)
    YF_BACKOFF_BASE    base seconds for backoff        (default 8)

After the run, `yahoo_rate_limiter.stats` holds counters you can log or
send to Telegram to see how rough the scan was:
    {'requests': N, 'retries': N, 'blocked_giveups': N}
"""
import os
import time
import random
import threading
import requests

MIN_DELAY = float(os.environ.get('YF_MIN_DELAY_SEC', '1.0'))
MAX_DELAY = float(os.environ.get('YF_MAX_DELAY_SEC', '2.2'))
MAX_RETRIES = int(os.environ.get('YF_MAX_RETRIES', '5'))
BACKOFF_BASE = float(os.environ.get('YF_BACKOFF_BASE', '8'))

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_lock = threading.Lock()
_last_call_ts = [0.0]

# Simple run stats so the pipeline can report how the scan went.
stats = {'requests': 0, 'retries': 0, 'blocked_giveups': 0}

_already_patched = getattr(requests.Session, '_yf_rate_limited', False)
_orig_request = requests.Session.request


def _paced_request(self, method, url, *args, **kwargs):
    # ---- pace requests so traffic looks human, not scripted ----
    with _lock:
        wait_target = random.uniform(MIN_DELAY, MAX_DELAY)
        elapsed = time.monotonic() - _last_call_ts[0]
        sleep_needed = wait_target - elapsed
        if sleep_needed > 0:
            time.sleep(sleep_needed)
        _last_call_ts[0] = time.monotonic()

    headers = dict(kwargs.pop('headers', None) or {})
    headers.setdefault('User-Agent', _BROWSER_UA)
    headers.setdefault('Accept-Language', 'en-US,en;q=0.9')
    kwargs['headers'] = headers
    kwargs.setdefault('timeout', 20)

    stats['requests'] += 1
    last_exc = None
    resp = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = _orig_request(self, method, url, *args, **kwargs)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_exc = exc
            sleep_s = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 3)
            stats['retries'] += 1
            print(f"[yahoo_rate_limiter] connection error on {url} "
                  f"(attempt {attempt + 1}/{MAX_RETRIES}), sleeping {sleep_s:.0f}s")
            time.sleep(sleep_s)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            sleep_s = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 3)
            stats['retries'] += 1
            print(f"[yahoo_rate_limiter] HTTP {resp.status_code} on {url} "
                  f"(attempt {attempt + 1}/{MAX_RETRIES}), sleeping {sleep_s:.0f}s")
            time.sleep(sleep_s)
            continue

        return resp

    # exhausted retries
    stats['blocked_giveups'] += 1
    if resp is not None:
        return resp  # let caller see the final (bad) response / raise_for_status
    raise last_exc


if not _already_patched:
    requests.Session.request = _paced_request
    requests.Session._yf_rate_limited = True
    print(f"[yahoo_rate_limiter] active: {MIN_DELAY:.1f}-{MAX_DELAY:.1f}s pacing, "
          f"{MAX_RETRIES} retries, backoff base {BACKOFF_BASE:.0f}s")
