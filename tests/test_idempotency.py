"""Creating an evaluation must not be retried; retrying one may be.

The API has no idempotency key. Repeating the same (video, prompt, model,
detectors) files a SECOND run with its own id and its own charge — so a client
that retries an ambiguous failure bills the caller twice for recovering from our
error, and the caller cannot tell, because the first response never arrived.
"""

from __future__ import annotations

import httpx
import pytest

from physionlabs import ConnectionError as GalileoConnectionError
from physionlabs import RateLimitError, ServerError

from .conftest import Recorder, err, fixture, ok


def _queued() -> dict:
    return {**fixture("evaluation_completed"), "id": "eval_1", "status": "queued"}


def test_create_sends_one_request_after_a_500(client_factory):
    rec = Recorder(err(500, "internal"), ok(_queued(), 201))
    with pytest.raises(ServerError):
        client_factory(rec, max_retries=5).evaluations.create(video={"url": "https://x/y.mp4"})
    assert len(rec.calls) == 1, "a second POST would be a second charged evaluation"


def test_create_sends_one_request_after_a_connection_failure(client_factory):
    # Worse than a 500: we do not know the request arrived. It may have arrived,
    # created the run, and lost the response.
    attempts = 0

    def boom(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("no route")

    with pytest.raises(GalileoConnectionError):
        client_factory(boom, max_retries=5).evaluations.create(video={"url": "https://x/y.mp4"})
    assert attempts == 1


def test_a_429_on_create_is_still_waited_out(client_factory):
    # A refusal is knowledge, not ambiguity: the server created nothing. Not
    # honouring this would make the no-retry rule useless in the one case where
    # retrying costs nothing.
    rec = Recorder(
        err(429, "rate_limited", **{"retry-after": "0"}),
        ok(_queued(), 201),
    )
    ev = client_factory(rec, max_retries=0).evaluations.create(video={"url": "https://x/y.mp4"})
    assert ev.id == "eval_1"
    assert len(rec.calls) == 2


def test_retry_is_retried_because_it_is_idempotent(client_factory):
    rec = Recorder(
        err(500, "internal"),
        ok({**fixture("evaluation_completed"), "id": "eval_2", "status": "queued", "retry_of": "eval_1"}, 201),
    )
    nxt = client_factory(rec, max_retries=2).evaluations.retry("eval_1")
    assert nxt.id == "eval_2"
    assert len(rec.calls) == 2, "a repeated retry is handed the same successor"


def test_retry_after_zero_forever_is_bounded_by_a_count(client_factory):
    # The bug: a budget measured in SLEEP does not bound a loop whose sleeps are
    # zero. With only that guard this spun as fast as the network allowed.
    calls = 0

    def limited(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return err(429, "rate_limited", **{"retry-after": "0"})

    with pytest.raises(RateLimitError):
        client_factory(limited, max_retries=0, max_rate_limit_retries=4).account.credits()
    assert calls == 5, "one attempt plus four absorbed 429s, then it gives up"


def test_the_wall_clock_deadline_also_ends_it(client_factory):
    calls = 0

    def limited(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return err(429, "rate_limited", **{"retry-after": "0.05"})

    with pytest.raises(RateLimitError):
        client_factory(
            limited, max_retries=0, max_rate_limit_retries=10_000, rate_limit_budget=0.2
        ).account.credits()
    assert 1 < calls < 10_000, f"absorbed {calls} — bounded by time, not by the count"
