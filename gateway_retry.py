"""Quota-aware retry for calls that may hit the real Data Gateway's Sheets-backed API.

This project's single Google service account has a *permanent* free-tier ceiling of 60 Sheets
API requests/minute, shared across every real spreadsheet it touches (see
server/gaps-in-services/Pending_Items.md). The Gateway's own internal retry
(server/services/12_data_gateway_service/app/clients/retry.py) only buys ~1.5 seconds of backoff
before giving up and returning HTTP 503 to the caller -- nowhere near enough to ride out a
sustained quota exhaustion, since the quota window is a rolling 60 seconds, not a daily cap.

This module is the test suite's own pacing layer on top of that: treat a 503 from the Gateway (or
a service sitting in front of it) as "wait for the window to roll over, then retry" rather than a
hard failure, matching this project's own documented convention ("don't assume a 429 means
blocked for the day").
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

# Rolling 60s window + margin for clock/measurement slop between this process and Google's.
QUOTA_BACKOFF_SECONDS = 70
# 3 attempts = up to ~210s worst case before giving up and letting the caller's own assertion
# produce a real failure -- long enough to survive one real quota exhaustion, short enough that
# a genuinely broken test doesn't hang the whole suite.
MAX_QUOTA_RETRIES = 3


def call_with_quota_backoff(
    fn: Callable[[], httpx.Response],
    max_retries: int = MAX_QUOTA_RETRIES,
    backoff_seconds: float = QUOTA_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Calls `fn()` (expected to perform one httpx request), retrying on a 503 with a long,
    quota-window-sized backoff instead of failing immediately.

    Not for eventual-consistency polling (e.g. waiting on a Kafka-delivered event to land) --
    each test file already has its own short local poll-loop for that, a different concern from
    quota pacing. This is specifically for "the Gateway itself rejected the call because the
    account is over its per-minute ceiling right now."
    """
    response: httpx.Response | None = None
    for attempt in range(max_retries):
        response = fn()
        if response.status_code != 503:
            return response
        if attempt < max_retries - 1:
            sleep_fn(backoff_seconds)
    assert response is not None
    return response
