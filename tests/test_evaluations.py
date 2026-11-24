"""Client's complete local-file flow, including failures before a paid submission."""
import json

import httpx
import pytest

from physionlabs import Client, InvalidRequestError, PollTimeoutError, ServerError
from .conftest import Recorder, fixture, ok, err


def client(rec):
    return Client(api_key="test", base_url="https://api.example",
                  upload_base_url="https://storage.example",
                  http_client=httpx.Client(transport=httpx.MockTransport(rec)))


def evaluation(status="completed"):
    return {**fixture("evaluation_completed"), "status": status, "model": "galileo-pm"}


def video(status="ready"):
    return {"id": "vid_1", "object": "video", "status": status,
            "cdn_url": "https://cdn.example/clip.mp4"}


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"test video bytes")
    return path


def test_create_uploads_validates_submits_then_waits(clip):
    rec = Recorder(ok({"video_id": "vid_1", "cdn_url": "https://cdn.example/clip.mp4",
                       "upload_path": "/upload"}), ok({}), ok(video("processing")),
                   ok(video()), ok(evaluation("queued")), ok(evaluation()))
    input = {"video": {"path": clip}, "prompt": "A ball rolls."}
    with client(rec) as c:
        result = c.evaluations.create(model="galileo-pm", input=input)
    assert result.status.value == "completed"
    assert result.model.value == "galileo-pm"
    assert [(r.method, r.url.path) for r in rec.calls] == [
        ("POST", "/v1/videos"), ("PUT", "/upload"), ("POST", "/v1/videos/vid_1/complete"),
        ("GET", "/v1/videos/vid_1"), ("POST", "/v1/evaluations"),
        ("GET", f"/v1/evaluations/{result.id}"),
    ]
    assert rec.calls[1].content == clip.read_bytes()
    assert "authorization" not in rec.calls[1].headers
    assert json.loads(rec.calls[4].content) == {
        "model": "galileo-pm", "input": {"video": {"upload_id": "vid_1"}, "prompt": "A ball rolls."},
    }
    assert input["video"] == {"path": clip}  # caller data is unchanged


@pytest.mark.parametrize("method", ["create", "submit"])
def test_failed_upload_never_submits(method, clip):
    rec = Recorder(ok({"video_id": "vid_1", "cdn_url": "https://cdn.example/clip.mp4",
                       "upload_path": "/upload"}), ok({}), ok(video("failed")))
    with client(rec) as c, pytest.raises(InvalidRequestError, match="vid_1"):
        getattr(c.evaluations, method)(model="galileo-pm", input={"video": {"path": str(clip)}})
    assert not any(r.url.path == "/v1/evaluations" for r in rec.calls)


def test_submit_reuses_upload_but_waits_for_validation_only(clip):
    rec = Recorder(ok({"video_id": "vid_1", "cdn_url": "https://cdn.example/clip.mp4", "skip_upload": True}),
                   ok(video("processing")), ok(video()), ok(evaluation("queued")))
    with client(rec) as c:
        result = c.evaluations.submit(model="galileo-pm", input={"video": {"path": clip}})
    assert result.status.value == "queued"
    assert not rec.of("PUT")
    assert len(rec.calls) == 4


@pytest.mark.parametrize("source", [{"url": "https://example.com/video.mp4"},
                                     {"upload_id": "vid_1"}, {"b64_json": "dmlkZW8="}])
def test_submit_remote_source_returns_without_polling(source):
    rec = Recorder(ok(evaluation("queued")))
    with client(rec) as c:
        result = c.evaluations.submit(model="galileo-pm", input={"video": source}, metadata={"job": 1})
    assert result.status.value == "queued"
    assert len(rec.calls) == 1
    assert json.loads(rec.calls[0].content) == {
        "model": "galileo-pm", "input": {"video": source}, "metadata": {"job": 1},
    }


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
def test_create_returns_every_terminal_status(status):
    final = evaluation(status)
    if status == "failed":
        final["result"] = None
    rec = Recorder(ok(evaluation("queued")), ok(final))
    with client(rec) as c:
        result = c.evaluations.create(model="galileo-pm", input={"video": {"url": "https://example.com/v.mp4"}})
    assert result.status.value == status
    assert len(rec.calls) == 2


def test_create_waits_through_pending_clip():
    # The server accepts a submission before its clip is ready and answers
    # `pending_clip`; rc7 rejected that response in validation.
    rec = Recorder(ok(evaluation("pending_clip"), 201), ok(evaluation("queued")), ok(evaluation()))
    with client(rec) as c:
        result = c.evaluations.create(model="galileo-pm", input={"video": {"upload_id": "vid_1"}})
    assert result.status.value == "completed"
    assert len(rec.of("POST")) == 1


def test_poll_timeout_preserves_id_and_does_not_resubmit():
    rec = Recorder(ok(evaluation("queued")), ok(evaluation("processing")))
    with client(rec) as c, pytest.raises(PollTimeoutError, match=evaluation()["id"]):
        c.evaluations.create(model="galileo-pm", input={"video": {"upload_id": "vid_1"}}, timeout=0)
    assert len(rec.of("POST")) == 1


@pytest.mark.parametrize("method", ["create", "submit"])
def test_ambiguous_submission_failure_is_never_retried(method):
    rec = Recorder(err(500, "internal_error"))
    with client(rec) as c, pytest.raises(ServerError):
        getattr(c.evaluations, method)(model="galileo-pm", input={"video": {"upload_id": "vid_1"}})
    assert len(rec.calls) == 1


@pytest.mark.parametrize("input", [{}, {"video": {"path": "x", "url": "https://example.com/x"}},
                                   {"video": {"url": ""}}, {"video": {"url": 4}},
                                   {"video": {"path": "x"}, "prompt": 123},
                                   {"video": {"path": "x"}, "typo": "oops"}])
def test_malformed_input_fails_before_upload(input):
    rec = Recorder()
    with client(rec) as c, pytest.raises(ValueError):
        c.evaluations.create(model="galileo-pm", input=input)
    assert not rec.calls


def test_models_list_parses_galileo_pm():
    # /v1/models lists galileo-pm, the only model an API key can use. rc8's
    # ModelId had no member for it, so `account.models()` raised on every call.
    with client(Recorder(ok(fixture("models")))) as c:
        listed = c.account.models()
    pm = next(m for m in listed.data if m.id.value == "galileo-pm")
    assert [d.value for d in pm.detectors] == ["prompt_misalignment"]


def test_models_list_containing_galileo_parses():
    # Internal accounts still see `galileo` on /v1/models (the fixture's captured
    # entry). Model.id is EvaluationModelId, not the request-only ModelId, so
    # that listing must parse rather than raise.
    with client(Recorder(ok(fixture("models")))) as c:
        listed = c.account.models()
    assert [m.id.value for m in listed.data] == ["galileo", "galileo-pm"]


def test_create_with_galileo_pm():
    final = {**evaluation(), "model": "galileo-pm"}
    rec = Recorder(ok({**final, "status": "queued"}), ok(final))
    with client(rec) as c:
        result = c.evaluations.create(model="galileo-pm", input={
            "video": {"url": "https://example.com/v.mp4"}, "prompt": "A ball rolls."})
    assert json.loads(rec.calls[0].content)["model"] == "galileo-pm"
    assert result.model.value == "galileo-pm"


@pytest.mark.parametrize("method", ["create", "submit"])
def test_model_defaults_to_galileo_pm(method):
    # The API requires `model` and offers API keys only galileo-pm, so a caller
    # who names no model gets the one model they can use.
    final = {**evaluation(), "model": "galileo-pm"}
    rec = Recorder(ok(final))
    with client(rec) as c:
        getattr(c.evaluations, method)(input={
            "video": {"url": "https://example.com/v.mp4"}, "prompt": "A ball rolls."})
    assert json.loads(rec.calls[0].content)["model"] == "galileo-pm"


def test_a_retired_model_is_refused_as_an_invalid_request():
    rec = Recorder(err(400, "model_not_available", "galileo-1.0 is not available on the API"))
    with client(rec) as c, pytest.raises(InvalidRequestError) as caught:
        c.evaluations.submit(model="galileo-1.0", input={
            "video": {"url": "https://example.com/v.mp4"}, "prompt": "A ball rolls."})
    assert caught.value.code == "model_not_available"
    assert len(rec.calls) == 1


def test_a_completed_galileo_pm_run_without_visual_glitch_fields_parses():
    # Accounts without Galileo access get no visual-glitch fields at all:
    # `summary.has_visual_glitch` is absent and only prompt_misalignment runs.
    # rc10 required the key, so retrieve/wait raised on every completed run.
    pm = next(g for g in fixture("evaluation_completed")["result"]["glitches"]
              if g["type"] == "prompt_misalignment")
    body = {**evaluation(), "model": "galileo-pm",
            "detectors": [{"status": "completed", "detector": "prompt_misalignment"}],
            "result": {"glitches": [pm, pm],
                       "summary": {"num_glitches": 2, "has_prompt_misalignment": True}}}
    with client(Recorder(ok(body))) as c:
        ev = c.evaluations.retrieve(body["id"])
    assert ev.result is not None
    assert ev.result.summary.has_prompt_misalignment is True
    assert ev.result.summary.has_visual_glitch is None
    assert [d.detector.value for d in ev.detectors or []] == ["prompt_misalignment"]
