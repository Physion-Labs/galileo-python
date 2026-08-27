"""One exception per thing a caller might actually do about it.

The split is by REACTION, not by status code. ``RateLimitError`` and
``InsufficientCreditsError`` are both a refusal, but one clears on its own and
the other needs somebody to buy credits -- which is the difference between a
batch that pauses and a batch that stops.
"""

from __future__ import annotations

from typing import Any

import httpx

__all__ = [
    "GalileoError",
    "APIError",
    "InvalidRequestError",
    "AuthenticationError",
    "NotFoundError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ServerError",
    "ConnectionError",
    "PollTimeoutError",
    "error_from_response",
]


class GalileoError(Exception):
    """Base class. Catch this to catch anything this client raises."""


class APIError(GalileoError):
    """The API answered, and the answer was a refusal."""

    def __init__(
        self,
        *,
        status: int,
        type: str,
        code: str,
        message: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.type = type
        self.code = code
        self.message = message
        #: Quote this when asking us about a specific failure.
        self.request_id = request_id

    def __str__(self) -> str:
        suffix = f" (request_id={self.request_id})" if self.request_id else ""
        return f"[{self.status} {self.code}] {self.message}{suffix}"


class InvalidRequestError(APIError):
    """The request was wrong: bad body, unsupported codec, video too large."""


class AuthenticationError(APIError):
    """The key is missing, malformed, or revoked."""


class NotFoundError(APIError):
    """No such evaluation or video, or not yours."""


class InsufficientCreditsError(APIError):
    """Out of credits. Retrying cannot help; the balance has to change."""


class RateLimitError(APIError):
    """Too many requests.

    Unlike the others this clears by waiting, and ``retry_after`` is how long the
    server asked for. The client already waits and retries inside its rate-limit
    budget, so seeing this means the budget ran out -- not that nothing was tried.
    """

    def __init__(self, *, retry_after: float | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.retry_after = retry_after


class ServerError(APIError):
    """Our fault: a 5xx, or a model that answered unusably."""


class ConnectionError(GalileoError):
    """The request never got an answer: DNS, TCP, TLS, a timeout.

    Separate from ``ServerError`` because the two differ in what is safe to
    assume. A 500 means the server received the request and may have acted on
    it; this means we do not know whether it arrived at all.
    """


class PollTimeoutError(GalileoError):
    """A wait that ran out of patience before the job settled.

    The job is still running. Retrieve it again later rather than resubmitting --
    a second submission is a second charge.
    """


_BY_STATUS: dict[int, type[APIError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: AuthenticationError,
    404: NotFoundError,
    413: InvalidRequestError,
    422: InvalidRequestError,
}


def retry_after_seconds(headers: httpx.Headers) -> float | None:
    """``Retry-After`` in seconds, or None when the server did not say.

    The header is defined as either a number of seconds or an HTTP date, and both
    appear in the wild. A date in the past yields 0 rather than a negative wait.
    """
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    import datetime as _dt

    now = _dt.datetime.now(tz=when.tzinfo or _dt.timezone.utc)
    return max(0.0, (when - now).total_seconds())


def error_from_response(response: httpx.Response) -> APIError:
    """Build the right exception from a response the server refused with.

    The body is not trusted to be well-formed. An error can come from a proxy, a
    load balancer, or a crash that never reached the application, and those answer
    with HTML or with nothing. Status is always there; everything else is a best
    effort.
    """
    parsed: dict[str, Any] = {}
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            parsed = body["error"]
    except Exception:
        pass

    status = response.status_code
    kw: dict[str, Any] = {
        "status": status,
        "type": parsed.get("type") or ("api_error" if status >= 500 else "invalid_request_error"),
        "code": parsed.get("code") or f"http_{status}",
        "message": parsed.get("message") or f"Galileo returned {status}.",
        "request_id": parsed.get("request_id") or response.headers.get("x-request-id"),
    }
    if status == 429:
        return RateLimitError(retry_after=retry_after_seconds(response.headers), **kw)
    return _BY_STATUS.get(status, ServerError)(**kw)
