"""Submit videos and read back what Galileo found."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .._poll import poll_until
from .._transport import Transport
from ..models import Evaluation, EvaluationList

# An evaluation stops changing at one of these.
#
# `partial` is terminal and is NOT an error: one detector finished and another did
# not. The result carries what was found and `detectors` says which of them to
# trust -- so a caller waiting for `completed` alone waits forever.
SETTLED = frozenset({"completed", "partial", "failed"})


class Evaluations:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def create(
        self,
        *,
        video: Mapping[str, Any],
        prompt: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        glitch_types: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Evaluation:
        """Queue an evaluation. Returns immediately, in ``queued``.

        ``video`` is one of ``{"url": ...}``, ``{"upload_id": ...}`` or
        ``{"b64_json": ...}``. Use :meth:`create_and_wait` unless you have your
        own polling.
        """
        body: dict[str, Any] = {"video": dict(video)}
        if prompt is not None:
            body["prompt"] = prompt
        if model is not None:
            body["model"] = model
        if model_version is not None:
            body["model_version"] = model_version
        if glitch_types is not None:
            body["glitch_types"] = list(glitch_types)
        if metadata is not None:
            body["metadata"] = dict(metadata)
        return Evaluation.model_validate(
            self._t.json(method="POST", path="/v1/evaluations", body=body)
        )

    def retrieve(self, evaluation_id: str) -> Evaluation:
        return Evaluation.model_validate(
            self._t.json(method="GET", path=f"/v1/evaluations/{evaluation_id}")
        )

    def list(self, *, limit: int | None = None, video_id: str | None = None) -> EvaluationList:
        """Your evaluations, newest first."""
        return EvaluationList.model_validate(
            self._t.json(
                method="GET",
                path="/v1/evaluations",
                params={"limit": limit, "video_id": video_id},
            )
        )

    def delete(self, evaluation_id: str) -> None:
        self._t.send(method="DELETE", path=f"/v1/evaluations/{evaluation_id}")

    def wait_until_settled(self, evaluation_id: str, *, timeout: float = 600.0) -> Evaluation:
        """Poll an existing evaluation until it stops changing."""
        return poll_until(
            lambda: self.retrieve(evaluation_id),
            lambda ev: ev.status.value in SETTLED,
            describe=f"evaluation {evaluation_id}",
            status_of=lambda ev: ev.status.value,
            timeout=timeout,
        )

    def create_and_wait(self, *, timeout: float = 600.0, **params: Any) -> Evaluation:
        """Submit and wait. What most callers want."""
        queued = self.create(**params)
        if queued.status.value in SETTLED:
            return queued
        return self.wait_until_settled(queued.id, timeout=timeout)
