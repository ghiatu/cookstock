#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yahoo_rate_limiter.py

Patches Python's `requests` library so every outgoing HTTP call
(made by `yahoofinancials`, which cookStock.py uses under the hood) is:
  1. paced with a randomized delay,
  2. sent with a realistic browser User-Agent header,
  3. optionally routed through a proxy (see YF_PROXY_URL below) - this
     matters a lot on GitHub-hosted runners, whose IPs come from shared
     AWS/Azure ranges that Yahoo Finance rate-limits/blocks at the IP
     level regardless of how politely YOUR code behaves, because many
     other unrelated bots share that same IP pool,
  4. retried with exponential backoff on HTTP 429 / 5xx / connection
     errors, UP TO a point - a circuit breaker (see below) detects when
     we're not just "briefly rate limited" but outright IP-blocked, and
     aborts fast instead of burning the whole job timeout on retries
     that can never succeed.

USAGE: import this module BEFORE `import cookStock` (or anything that
imports `yahoofinancials`). The patch is applied at import time.

    import yahoo_rate_limiter   # <- must come first
    import cookStock

Tunable via environment variables (all optional):
    YF_MIN_DELAY_SEC     min seconds between requests      (default 1.0)
    YF_MAX_DELAY_SEC     max seconds between requests       (default 2.2)
    YF_MAX_RETRIES       retries per request                (default 5)
    YF_BACKOFF_BASE      base seconds for backoff           (default 8)
    YF_PROXY_URL         e.g. http://user:pass@host:port -
                          routes every request through this proxy.
                          Recommended when running on GitHub-hosted
                          runners, since Yahoo blocks their shared IPs.
    YF_CIRCUIT_THRESHOLD consecutive blocked requests before
                          giving up on the whole run             (default 12)

After the run, `yahoo_rate_limiter.stats` holds counters you can log or
send to Telegram:
    {'requests': N, 'retries': N, 'blocked_giveups': N, 'consecutive_blocked': N}

If the circuit breaker trips, a `YahooBlockedError` is raised - catch
this in the pipeline to stop the scan early with a clear message instead
of retrying every remaining ticker for hours.
"""
import os
import time
import random
import threading
import requests

MIN_DELAY = float(os.environ.get('YF_MIN_DELAY_SEC', '1.0'))
MAX_DELAY = float(os.environ.get('YF_MAX_DELAY_SEC', '2.2'))
MAX_RETRIES = int(os.environ.get('YF_MAX_RETRIES', '3'))
BACKOFF_BASE = float(os.environ.get('YF_BACKOFF_BASE', '5'))
PROXY_URL = os.environ.get('YF_PROXY_URL', '').strip()
CIRCUIT_THRESHOLD = int(os.environ.get('YF_CIRCUIT_THRESHOLD', '6'))

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_lock = threading.Lock()
_last_call_ts = [0.0]

stats = {'requests': 0, 'retries': 0, 'blocked_giveups': 0, 'consecutive_blocked': 0}


class YahooBlockedError(Exception):
    """Raised when many requests in a row were rate-limited/blocked -
    almost always means the whole IP is blocked, not just this request.
    Retrying more won't help; the caller should stop and report this."""
    pass


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

    if PROXY_URL and 'proxies' not in kwargs:
        kwargs['proxies'] = {'http': PROXY_URL, 'https': PROXY_URL}

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

        # success - reset the circuit breaker counter
        stats['consecutive_blocked'] = 0
        return resp

    # exhausted retries for this one request - count it toward the circuit breaker
    stats['blocked_giveups'] += 1
    stats['consecutive_blocked'] += 1

    if stats['consecutive_blocked'] >= CIRCUIT_THRESHOLD:
        raise YahooBlockedError(
            f"{stats['consecutive_blocked']} requests in a row were rate-limited/"
            f"blocked even after {MAX_RETRIES} retries each. This is almost always "
            f"Yahoo Finance blocking this machine's IP address outright (very common "
            f"on GitHub-hosted runners, whose IPs are shared with many other bots) "
            f"rather than a temporary rate limit. Retrying further will not help. "
            f"Consider routing through a proxy (set YF_PROXY_URL) or running on a "
            f"self-hosted runner with a dedicated IP."
        )

    if resp is not None:
        return resp  # let caller see the final (bad) response / raise_for_status
    raise last_exc


if not _already_patched:
    requests.Session.request = _paced_request
    requests.Session._yf_rate_limited = True
    proxy_note = f", proxy ON" if PROXY_URL else ""
    print(f"[yahoo_rate_limiter] active: {MIN_DELAY:.1f}-{MAX_DELAY:.1f}s pacing, "
          f"{MAX_RETRIES} retries, backoff base {BACKOFF_BASE:.0f}s, "
          f"circuit breaker at {CIRCUIT_THRESHOLD} consecutive blocks{proxy_note}")

