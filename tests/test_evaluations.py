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
    return {**fixture("evaluation_completed"), "status": status, "model": "galileo-1.0"}


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
        result = c.evaluations.create(model="galileo-1.0", input=input)
    assert result.status.value == "completed"
    assert result.model.value == "galileo-1.0"
    assert [(r.method, r.url.path) for r in rec.calls] == [
        ("POST", "/v1/videos"), ("PUT", "/upload"), ("POST", "/v1/videos/vid_1/complete"),
        ("GET", "/v1/videos/vid_1"), ("POST", "/v1/evaluations"),
        ("GET", f"/v1/evaluations/{result.id}"),
    ]
    assert rec.calls[1].content == clip.read_bytes()
    assert "authorization" not in rec.calls[1].headers
    assert json.loads(rec.calls[4].content) == {
        "model": "galileo-1.0", "input": {"video": {"upload_id": "vid_1"}, "prompt": "A ball rolls."},
    }
    assert input["video"] == {"path": clip}  # caller data is unchanged


@pytest.mark.parametrize("method", ["create", "submit"])
def test_failed_upload_never_submits(method, clip):
    rec = Recorder(ok({"video_id": "vid_1", "cdn_url": "https://cdn.example/clip.mp4",
                       "upload_path": "/upload"}), ok({}), ok(video("failed")))
    with client(rec) as c, pytest.raises(InvalidRequestError, match="vid_1"):
        getattr(c.evaluations, method)(model="galileo-1.0", input={"video": {"path": str(clip)}})
    assert not any(r.url.path == "/v1/evaluations" for r in rec.calls)


def test_submit_reuses_upload_but_waits_for_validation_only(clip):
    rec = Recorder(ok({"video_id": "vid_1", "cdn_url": "https://cdn.example/clip.mp4", "skip_upload": True}),
                   ok(video("processing")), ok(video()), ok(evaluation("queued")))
    with client(rec) as c:
        result = c.evaluations.submit(model="galileo-1.0", input={"video": {"path": clip}})
    assert result.status.value == "queued"
    assert not rec.of("PUT")
    assert len(rec.calls) == 4


@pytest.mark.parametrize("source", [{"url": "https://example.com/video.mp4"},
                                     {"upload_id": "vid_1"}, {"b64_json": "dmlkZW8="}])
def test_submit_remote_source_returns_without_polling(source):
    rec = Recorder(ok(evaluation("queued")))
    with client(rec) as c:
        result = c.evaluations.submit(model="galileo-1.0", input={"video": source}, metadata={"job": 1})
    assert result.status.value == "queued"
    assert len(rec.calls) == 1
    assert json.loads(rec.calls[0].content) == {
        "model": "galileo-1.0", "input": {"video": source}, "metadata": {"job": 1},
    }


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
def test_create_returns_every_terminal_status(status):
    final = evaluation(status)
    if status == "failed":
        final["result"] = None
    rec = Recorder(ok(evaluation("queued")), ok(final))
    with client(rec) as c:
        result = c.evaluations.create(model="galileo-1.0", input={"video": {"url": "https://example.com/v.mp4"}})
    assert result.status.value == status
    assert len(rec.calls) == 2


def test_poll_timeout_preserves_id_and_does_not_resubmit():
    rec = Recorder(ok(evaluation("queued")), ok(evaluation("processing")))
    with client(rec) as c, pytest.raises(PollTimeoutError, match=evaluation()["id"]):
        c.evaluations.create(model="galileo-1.0", input={"video": {"upload_id": "vid_1"}}, timeout=0)
    assert len(rec.of("POST")) == 1


@pytest.mark.parametrize("method", ["create", "submit"])
def test_ambiguous_submission_failure_is_never_retried(method):
    rec = Recorder(err(500, "internal_error"))
    with client(rec) as c, pytest.raises(ServerError):
        getattr(c.evaluations, method)(model="galileo-1.0", input={"video": {"upload_id": "vid_1"}})
    assert len(rec.calls) == 1


@pytest.mark.parametrize("input", [{}, {"video": {"path": "x", "url": "https://example.com/x"}},
                                   {"video": {"url": ""}}, {"video": {"url": 4}},
                                   {"video": {"path": "x"}, "prompt": 123},
                                   {"video": {"path": "x"}, "typo": "oops"}])
def test_malformed_input_fails_before_upload(input):
    rec = Recorder()
    with client(rec) as c, pytest.raises(ValueError):
        c.evaluations.create(model="galileo-1.0", input=input)
    assert not rec.calls
