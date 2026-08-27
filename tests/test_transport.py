"""What the transport does when the API says no."""

from __future__ import annotations

import pytest

from physionlabs import InsufficientCreditsError, RateLimitError, ServerError

from .conftest import Recorder, err, fixture, ok


def test_the_key_travels_as_a_bearer_token(client_factory):
    rec = Recorder(ok(fixture("account")))
    client_factory(rec).account.retrieve()
    assert rec.calls[0].headers["authorization"] == "Bearer gk_live_test"


def test_status_carries_no_key_so_it_answers_when_the_key_is_the_problem(client_factory):
    rec = Recorder(ok({"state": "operational", "checked_at": 1, "components": []}))
    client_factory(rec).account.status()
    assert "authorization" not in rec.calls[0].headers


def test_a_500_is_retried(client_factory):
    rec = Recorder(err(500, "internal"), ok(fixture("credits")))
    client_factory(rec, max_retries=2).account.credits()
    assert len(rec.calls) == 2


def test_a_500_that_keeps_failing_is_raised_not_retried_forever(client_factory):
    rec = Recorder(*[err(500, "internal") for _ in range(3)])
    with pytest.raises(ServerError):
        client_factory(rec, max_retries=2).account.credits()
    assert len(rec.calls) == 3, "one attempt plus two retries"


def test_a_model_that_answered_unusably_is_not_retried(client_factory):
    # The same input decodes to the same unusable answer, and the run is metered:
    # retrying spends the caller's credits again on a decided failure.
    rec = Recorder(err(502, "model_output_invalid"))
    with pytest.raises(ServerError):
        client_factory(rec, max_retries=3).evaluations.create(video={"url": "https://x/y.mp4"})
    assert len(rec.calls) == 1


def test_a_402_is_not_retried_because_waiting_cannot_change_a_balance(client_factory):
    rec = Recorder(err(402, "insufficient_credits"))
    with pytest.raises(InsufficientCreditsError):
        client_factory(rec, max_retries=3).evaluations.create(video={"url": "https://x/y.mp4"})
    assert len(rec.calls) == 1


def test_a_429_is_waited_out_and_the_wait_is_not_charged_to_the_retry_count(client_factory):
    rec = Recorder(
        err(429, "rate_limited", **{"retry-after": "0"}),
        err(429, "rate_limited", **{"retry-after": "0"}),
        err(429, "rate_limited", **{"retry-after": "0"}),
        ok({**fixture("evaluation_completed"), "id": "eval_1", "status": "queued"}, 201),
    )
    # max_retries=0: were rate limiting charged to it, the first 429 would raise.
    ev = client_factory(rec, max_retries=0).evaluations.create(video={"url": "https://x/y.mp4"})
    assert ev.id == "eval_1"
    assert len(rec.calls) == 4


def test_a_429_past_the_budget_raises_and_says_how_long_the_server_asked_for(client_factory):
    rec = Recorder(err(429, "rate_limited", **{"retry-after": "30"}))
    with pytest.raises(RateLimitError) as caught:
        client_factory(rec, rate_limit_budget=1.0).account.credits()
    assert caught.value.retry_after == 30.0


def test_a_non_json_error_body_still_produces_a_typed_error(client_factory):
    import httpx

    rec = Recorder(httpx.Response(502, text="<html>502 Bad Gateway</html>"))
    with pytest.raises(ServerError) as caught:
        client_factory(rec, max_retries=0).account.credits()
    assert caught.value.status == 502
