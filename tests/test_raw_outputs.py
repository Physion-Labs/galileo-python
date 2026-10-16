"""`output_raw=True`: an internal account gets the run's raw model outputs attached.

The server is the gate (`raw_outputs` capability, 403 otherwise); these tests pin
what the client does around it -- fetch once, after the run settles, never for a
failed run, and never lose a settled (paid-for) evaluation to a failed fetch.
"""
import httpx
import pytest

from physionlabs import (
    AuthenticationError,
    Client,
    EvaluationWithRaw,
    NotFoundError,
    PermissionDeniedError,
    RawOutputsError,
)
from physionlabs.resources.evaluations import RAW_TIMEOUT
from .conftest import Recorder, err, fixture, ok

RAW = {
    "object": "raw_outputs",
    "eval_id": "eval_1",
    "proposals": {"proposals": [{"id": "p1"}]},
    "verdicts": [{"id": "p1", "verdict": "rejected", "reason": "not a glitch"}],
    "misalignment": {"raw": "..."},
    "intermediates": {"object_tracks": {"tracks": [{"track_id": 1, "nodes": []}]}},
    "archived": "r2://bucket/eval_1.raw.json",
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("physionlabs._poll.time.sleep", lambda _s: None)


def client(rec):
    return Client(api_key="test", base_url="https://api.example",
                  upload_base_url="https://storage.example",
                  http_client=httpx.Client(transport=httpx.MockTransport(rec)))


def evaluation(status="completed"):
    return {**fixture("evaluation_completed"), "status": status, "model": "galileo-1.0"}


def paths(rec):
    return [(r.method, r.url.path) for r in rec.calls]


def test_create_fetches_raw_once_after_the_run_settles():
    ev_id = evaluation()["id"]
    rec = Recorder(ok(evaluation("queued")), ok(evaluation("processing")), ok(evaluation()), ok(RAW))
    with client(rec) as c:
        result = c.evaluations.create(
            model="galileo-1.0", input={"video": {"url": "https://cdn.example/a.mp4"}},
            output_raw=True,
        )
    assert isinstance(result, EvaluationWithRaw)
    assert result.raw == RAW
    assert result.raw["intermediates"]["object_tracks"]["tracks"][0]["track_id"] == 1
    assert result.raw_pruned is False
    # Polled twice, raw fetched exactly once and only at the end.
    assert paths(rec) == [
        ("POST", "/v1/evaluations"),
        ("GET", f"/v1/evaluations/{ev_id}"),
        ("GET", f"/v1/evaluations/{ev_id}"),
        ("GET", f"/v1/evaluations/{ev_id}/raw"),
    ]


def test_raw_gets_its_own_longer_timeout():
    rec = Recorder(ok(evaluation()), ok(RAW))
    with client(rec) as c:
        c.evaluations.retrieve("eval_1", output_raw=True)
    assert rec.calls[1].extensions["timeout"]["read"] == RAW_TIMEOUT
    assert rec.calls[0].extensions["timeout"]["read"] != RAW_TIMEOUT


def test_default_is_off_and_fetches_nothing_extra():
    rec = Recorder(ok(evaluation()))
    with client(rec) as c:
        result = c.evaluations.retrieve("eval_1")
    assert not isinstance(result, EvaluationWithRaw)
    assert len(rec.calls) == 1


def test_a_pruned_payload_says_so():
    pruned = {**RAW, "proposals": None, "verdicts": None, "misalignment": None, "intermediates": None}
    rec = Recorder(ok(evaluation()), httpx.Response(200, json=pruned, headers={"X-Raw-Outputs": "pruned"}))
    with client(rec) as c:
        result = c.evaluations.retrieve("eval_1", output_raw=True)
    assert result.raw_pruned is True
    assert result.raw["archived"] == RAW["archived"]


def test_a_failed_run_never_asks_for_raw():
    rec = Recorder(ok(evaluation("failed")))
    with client(rec) as c:
        result = c.evaluations.retrieve("eval_1", output_raw=True)
    assert isinstance(result, EvaluationWithRaw)
    assert result.raw is None
    assert len(rec.calls) == 1


def test_an_account_without_the_capability_keeps_its_evaluation():
    """403 must not cost the caller a settled, paid-for run."""
    rec = Recorder(ok(evaluation()), err(403, "forbidden", "raw outputs are internal"))
    with client(rec) as c, pytest.raises(RawOutputsError) as caught:
        c.evaluations.retrieve("eval_1", output_raw=True)
    assert caught.value.evaluation.status.value == "completed"
    assert caught.value.evaluation.raw is None
    assert isinstance(caught.value.__cause__, PermissionDeniedError)


def test_a_run_with_no_raw_outputs_is_reported_not_swallowed():
    rec = Recorder(ok(evaluation()), err(404, "not_found", "no raw model outputs"))
    with client(rec) as c, pytest.raises(RawOutputsError) as caught:
        c.evaluations.retrieve("eval_1", output_raw=True)
    assert isinstance(caught.value.__cause__, NotFoundError)


def test_403_is_still_an_authentication_error_for_existing_callers():
    rec = Recorder(err(403, "forbidden"))
    with client(rec) as c, pytest.raises(AuthenticationError) as caught:
        c.evaluations.retrieve("eval_1")
    assert isinstance(caught.value, PermissionDeniedError)
