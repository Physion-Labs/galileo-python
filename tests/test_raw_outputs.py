import httpx
import pytest

from physionlabs import Client, EvaluationWithRaw
from physionlabs.resources.evaluations import RAW_TIMEOUT

from .conftest import Recorder, fixture, ok

RAW = {"proposals": {"proposals": []}, "verdicts": [], "intermediates": {"object_tracks": {"tracks": []}}}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("physionlabs._poll.time.sleep", lambda _s: None)


def client(rec):
    return Client(api_key="test", base_url="https://api.example",
                  http_client=httpx.Client(transport=httpx.MockTransport(rec)))


def evaluation(status="completed"):
    return {**fixture("evaluation_completed"), "status": status, "model": "galileo-1.0"}


def test_create_fetches_raw_once_after_settling():
    ev_id = evaluation()["id"]
    rec = Recorder(ok(evaluation("queued")), ok(evaluation("processing")), ok(evaluation()), ok(RAW))
    with client(rec) as c:
        ev = c.evaluations.create(model="galileo-1.0", input={"video": {"url": "https://x/a.mp4"}},
                                  output_raw=True)
    assert isinstance(ev, EvaluationWithRaw)
    assert ev.raw == RAW and ev.raw_pruned is False
    assert [r.url.path for r in rec.calls][-2:] == [f"/v1/evaluations/{ev_id}", f"/v1/evaluations/{ev_id}/raw"]
    assert rec.calls[-1].extensions["timeout"]["read"] == RAW_TIMEOUT


def test_pruned_header():
    rec = Recorder(ok(evaluation()), httpx.Response(200, json=RAW, headers={"X-Raw-Outputs": "pruned"}))
    with client(rec) as c:
        assert c.evaluations.retrieve("eval_1", output_raw=True).raw_pruned is True


def test_off_by_default_and_skipped_for_failed_runs():
    rec = Recorder(ok(evaluation()), ok(evaluation("failed")))
    with client(rec) as c:
        assert not isinstance(c.evaluations.retrieve("eval_1"), EvaluationWithRaw)
        assert c.evaluations.retrieve("eval_1", output_raw=True).raw is None
    assert len(rec.calls) == 2
