"""A fake server, so no test touches the network.

The response bodies come from `tests/fixtures/`, which were CAPTURED from the
real API (`scripts/capture_fixtures.py`) rather than written by hand. The first
draft of these tests invented them, and three bodies were missing required fields
the real API always sends — so the tests failed on the fixtures rather than on the
code, which is the least useful kind of red.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def fixture(name: str) -> Any:
    """One captured response body."""
    return json.loads((FIXTURES / f"{name}.json").read_text())

from physionlabs import Galileo


class Recorder:
    """Answers from a script, and remembers what it was asked."""

    def __init__(self, *responses: httpx.Response | Callable[[httpx.Request], httpx.Response]):
        self.queue = list(responses)
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if not self.queue:
            raise AssertionError(f"unexpected call {len(self.calls)} to {request.url}")
        nxt = self.queue.pop(0)
        return nxt(request) if callable(nxt) else nxt

    def of(self, method: str) -> list[httpx.Request]:
        return [c for c in self.calls if c.method == method]


def ok(body: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def err(status: int, code: str, message: str = "no", **headers: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"type": "api_error", "code": code, "message": message, "request_id": "req_1"}},
        headers=headers,
    )


@pytest.fixture
def client_factory():
    """Build a Galileo whose HTTP goes to a Recorder instead of the network."""

    made: list[Galileo] = []

    def build(recorder: Any, **kw: Any) -> Galileo:
        # A bare handler is accepted alongside a Recorder, so a test that needs to
        # RAISE (a connection failure has no response to script) can pass a
        # function instead of pretending it is a queue of replies.
        http = httpx.Client(transport=httpx.MockTransport(recorder))
        galileo = Galileo(
            api_key="gk_live_test",
            base_url="https://api.example",
            upload_base_url="https://uploads.example",
            http_client=http,
            **kw,
        )
        made.append(galileo)
        return galileo

    yield build
    for g in made:
        g.close()
