"""Wait for something asynchronous to settle.

Backs off rather than polling at a fixed rate: a job that finishes in two seconds
should be noticed quickly, and one that takes three minutes should not be asked
about ninety times.
"""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from .errors import PollTimeoutError

T = TypeVar("T")


def poll_until(
    fetch_once: Callable[[], T],
    settled: Callable[[T], bool],
    *,
    describe: str,
    status_of: Callable[[T], str] | None = None,
    timeout: float = 600.0,
    initial_interval: float = 1.0,
    max_interval: float = 8.0,
) -> T:
    interval = initial_interval
    deadline = time.monotonic() + timeout

    while True:
        value = fetch_once()
        if settled(value):
            return value
        if time.monotonic() + interval > deadline:
            status = f" (last status: {status_of(value)})" if status_of else ""
            raise PollTimeoutError(
                f"{describe} did not settle within {timeout:.0f}s{status}. "
                "It is still running; retrieve it again later."
            )
        time.sleep(interval)
        interval = min(interval * 1.5, max_interval)
