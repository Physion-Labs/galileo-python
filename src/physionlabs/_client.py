"""The client. One object, three resources, no configuration beyond a key."""

from __future__ import annotations

import os
from types import TracebackType

import httpx

from ._transport import Transport
from .resources import Account, Evaluations, Videos

DEFAULT_BASE_URL = "https://api.physionlabs.ai"


class Galileo:
    """Client for the Galileo video evaluation API.

    ``api_key`` defaults to ``GALILEO_API_KEY`` from the environment, rather than
    being required as an argument, because the alternative is a key written into a
    source file -- and a key in a source file is a key in somebody's git history.

    Usable as a context manager, which closes the underlying HTTP connections::

        with Galileo() as galileo:
            ...
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        upload_base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        rate_limit_budget: float = 60.0,
        max_rate_limit_retries: int = 20,
        max_concurrency: int = 4,
        http_client: httpx.Client | None = None,
    ) -> None:
        key = api_key or os.environ.get("GALILEO_API_KEY")
        if not key:
            raise ValueError(
                "No API key. Pass api_key=, or set GALILEO_API_KEY in the environment."
            )
        resolved_base = (base_url or DEFAULT_BASE_URL).rstrip("/")

        self._transport = Transport(
            api_key=key,
            base_url=resolved_base,
            timeout=timeout,
            max_retries=max_retries,
            rate_limit_budget=rate_limit_budget,
            max_rate_limit_retries=max_rate_limit_retries,
            max_concurrency=max_concurrency,
            client=http_client,
        )

        self.evaluations = Evaluations(self._transport)
        # `upload_base_url` is separate from `base_url` because the two genuinely
        # differ: uploads go to storage infrastructure, and pinning them together
        # would send the bytes to whichever host happens to serve the API.
        self.videos = Videos(self._transport, upload_base_url or resolved_base)
        self.account = Account(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Galileo:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
