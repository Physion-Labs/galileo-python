"""Explicit release smoke test: run two evaluations on the selected deployment."""
import os
from pathlib import Path

from physionlabs import Client

assert os.environ.get("GALILEO_API_KEY"), "GALILEO_API_KEY is required"
assert os.environ.get("GALILEO_TEST_VIDEO_URL"), "GALILEO_TEST_VIDEO_URL is required"
with Client(base_url=os.environ["GALILEO_BASE_URL"]) as client:
    local = client.evaluations.create(
        model="galileo-1.0",
        input={"video": {"path": Path(__file__).resolve().parents[1] / "tests/fixtures/release.mp4"}},
    )
    assert local.status.value == "completed", local.error
    assert local.result is not None
    print("Local file → automatic upload → create:", local.id, local.status.value)

    job = client.evaluations.submit(
        model="galileo-1.0",
        input={
            "video": {"url": os.environ["GALILEO_TEST_VIDEO_URL"]},
            "prompt": "A red background fills the frame.",
        },
    )
    assert job.id
    current = client.evaluations.retrieve(job.id)
    assert current.id == job.id
    print("URL + prompt → submit → retrieve:", current.id, current.status.value)
    result = client.evaluations.wait_until_settled(job.id)
    assert result.status.value == "completed", result.error
    assert result.result is not None
    print("Wait for submitted evaluation:", result.id, result.status.value)
