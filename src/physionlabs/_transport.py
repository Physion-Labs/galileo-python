"""HTTP: auth, timeouts, retries, rate-limit backoff, bounded concurrency.

A script calling this API once needs none of this. A job pushing a few hundred
clips through it needs all of it, and needs it to behave the same on every call
rather than be remembered at each call site.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, BinaryIO, Iterator, Mapping

import httpx

from .errors import ConnectionError as GalileoConnectionError
from .errors import error_from_response, retry_after_seconds

# Codes that are terminal despite a retryable status.
#
# `model_output_invalid` is a 502: the model answered, and answered unusably.
# The same input produces the same unusable answer, so a retry cannot change the
# outcome -- and the run is metered, so it would spend the caller's credits again
# on a failure that is already decided.
#
# `model_timeout` (504) is deliberately absent. There the model was still working
# when the gateway gave up, and a second attempt may well land.
TERMINAL_CODES = frozenset({"model_output_invalid", "unsupported_codec", "file_too_large"})

RETRYABLE_STATUS = frozenset({408, 409, 500, 502, 503, 504})


class Transport:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        rate_limit_budget: float = 60.0,
        max_concurrency: int = 4,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        # A budget of its own, separate from `max_retries`, because a rate-limit
        # reply is flow control rather than failure. Charged to the retry count, a
        # batch larger than that count fails on its own tail: submit ten things
        # against a limit that admits two a minute and the last must wait minutes,
        # which no sane retry count covers.
        self._rate_limit_budget = rate_limit_budget
        # Python has no ambient limit either. A ThreadPoolExecutor over two
        # hundred clips otherwise opens two hundred requests, most of which come
        # straight back 429 and spend the budget above on requests that were never
        # going to be admitted.
        self._gate = threading.Semaphore(max_concurrency)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def json(self, **spec: Any) -> Any:
        response = self.send(**spec)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def send(
        self,
        *,
        method: str,
        path: str | None = None,
        absolute_url: str | None = None,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        content: bytes | BinaryIO | Iterator[bytes] | None = None,
        content_type: str | None = None,
        content_length: int | None = None,
        anonymous: bool = False,
        max_retries: int | None = None,
    ) -> httpx.Response:
        if absolute_url is None and path is None:
            raise ValueError("a request needs either `path` or `absolute_url`")
        url = absolute_url or f"{self._base_url}{path}"
        retries = self._max_retries if max_retries is None else max_retries

        headers: dict[str, str] = {"accept": "application/json"}
        if not anonymous:
            headers["authorization"] = f"Bearer {self._api_key}"
        if content is not None:
            headers["content-type"] = content_type or "application/octet-stream"
            if content_length is None:
                raise ValueError("a streamed body must declare content_length")
            # Declared explicitly: a receiver that has to refuse an oversized body
            # before storing it cannot do so without knowing the size up front.
            headers["content-length"] = str(content_length)

        query = {k: v for k, v in (params or {}).items() if v is not None}

        with self._gate:
            return self._attempt(
                method=method,
                url=url,
                headers=headers,
                query=query,
                body=body,
                content=content,
                retries=retries,
            )

    def _attempt(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        query: dict[str, Any],
        body: Any,
        content: Any,
        retries: int,
    ) -> httpx.Response:
        rate_limit_spent = 0.0
        attempt = 0

        while True:
            try:
                response = self._client.request(
                    method,
                    url,
                    headers=headers,
                    params=query or None,
                    json=body if content is None else None,
                    content=content,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                # A streamed body cannot be replayed -- the file position has
                # moved -- so a retry would send a truncated request. Uploads pass
                # retries=0 anyway; this is the guard for anyone who does not.
                if attempt < retries and content is None:
                    attempt += 1
                    time.sleep(_backoff(attempt))
                    continue
                raise GalileoConnectionError(f"Could not reach Galileo at {url}: {exc}") from exc

            if response.is_success:
                return response

            if response.status_code == 429:
                wait = retry_after_seconds(response.headers)
                if wait is None:
                    wait = _backoff(attempt + 1)
                if rate_limit_spent + wait <= self._rate_limit_budget:
                    rate_limit_spent += wait
                    time.sleep(wait)
                    continue
                raise error_from_response(response)

            error = error_from_response(response)
            if (
                attempt < retries
                and content is None
                and response.status_code in RETRYABLE_STATUS
                and error.code not in TERMINAL_CODES
            ):
                attempt += 1
                time.sleep(_backoff(attempt))
                continue
            raise error


def _backoff(attempt: int) -> float:
    """Exponential, with jitter so a batch that fails together does not retry together."""
    base = min(0.5 * 2.0 ** (attempt - 1), 8.0)
    return base + random.random() * base * 0.25
