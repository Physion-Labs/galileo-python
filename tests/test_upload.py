"""The three-call upload, driven by a fake server.

The test that matters most is `test_the_put_carries_no_authorization_header`.
Everything else here is shape; that one is the difference between an upload and a
leaked credential.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from physionlabs import InvalidRequestError

from .conftest import Recorder, ok

BYTES = b"not really an mp4, but it has a length and a hash"


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(BYTES)
    return path


def _video(status: str = "ready") -> dict:
    return {
        "id": "vid_1",
        "object": "video",
        "status": status,
        "cdn_url": "https://cdn.example.com/vid_1.mp4",
    }


def _three_calls(status: str = "ready") -> Recorder:
    return Recorder(
        ok({"video_id": "vid_1", "cdn_url": "https://cdn.example.com/vid_1.mp4",
            "upload_path": "/v1/uploads?key=a&token=b"}, 201),
        httpx.Response(200, json={"ok": True}),
        ok(_video(status)),
    )


def test_upload_makes_three_calls_in_order(client_factory, clip):
    rec = _three_calls()
    video = client_factory(rec).videos.upload(clip)

    assert video.status.value == "ready"
    assert [f"{c.method} {c.url}" for c in rec.calls] == [
        "POST https://api.example/v1/videos",
        "PUT https://uploads.example/v1/uploads?key=a&token=b",
        "POST https://api.example/v1/videos/vid_1/complete",
    ]


def test_the_reservation_declares_the_real_size_and_the_real_hash(client_factory, clip):
    rec = _three_calls()
    client_factory(rec).videos.upload(clip)

    body = json.loads(rec.calls[0].content)
    assert body["size_bytes"] == len(BYTES)
    assert body["content_type"] == "video/mp4"
    assert body["content_hash"] == hashlib.sha256(BYTES).hexdigest()


def test_the_put_carries_no_authorization_header(client_factory, clip):
    rec = _three_calls()
    client_factory(rec).videos.upload(clip)

    put = rec.of("PUT")[0]
    assert "authorization" not in put.headers, "a key sent to storage is a key disclosed"
    # And the calls that DO go to the API still carry it, so this is not a blanket
    # failure to authenticate.
    for call in rec.calls:
        if str(call.url).startswith("https://api.example"):
            assert call.headers["authorization"] == "Bearer gk_live_test"


def test_the_put_declares_content_length_and_the_right_type(client_factory, clip):
    rec = _three_calls()
    client_factory(rec).videos.upload(clip)

    put = rec.of("PUT")[0]
    assert put.headers["content-length"] == str(len(BYTES))
    assert put.headers["content-type"] == "video/mp4"
    assert put.content == BYTES


def test_content_already_held_means_no_put_and_no_completion(client_factory, clip):
    rec = Recorder(
        ok({"video_id": "vid_dup", "cdn_url": "https://cdn.example.com/d.mp4", "skip_upload": True}, 201),
        ok({**_video(), "id": "vid_dup"}),
    )
    video = client_factory(rec).videos.upload(clip)

    assert video.id == "vid_dup"
    assert rec.of("PUT") == []
    assert not any("/complete" in str(c.url) for c in rec.calls)


def test_dedupe_false_sends_no_hash(client_factory, clip):
    rec = _three_calls()
    client_factory(rec).videos.upload(clip, dedupe=False)
    assert "content_hash" not in json.loads(rec.calls[0].content)


def test_an_empty_file_is_refused_before_anything_is_sent(client_factory, tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    rec = Recorder()
    with pytest.raises(InvalidRequestError):
        client_factory(rec).videos.upload(empty)
    assert rec.calls == [], "the caller should learn before spending a request"


def test_a_video_that_fails_validation_is_returned_not_raised(client_factory, clip):
    rec = _three_calls("failed")
    video = client_factory(rec).videos.upload(clip)
    assert video.status.value == "failed", "a rejected file is an outcome to inspect"
