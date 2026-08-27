"""Submit videos and read back what Galileo found."""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence

from .._poll import poll_until
from .._transport import Transport
from ..models import Evaluation, EvaluationCounts, EvaluationList

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
            self._t.json(
                method="POST",
                path="/v1/evaluations",
                body=body,
                # NEVER RETRIED, and this is the single most expensive default in
                # the client to get wrong.
                #
                # Submission is not idempotent: the API has no idempotency key,
                # and repeating the same (video, prompt, model, detectors) files a
                # SECOND run with its own id and its own charge. So every failure
                # that leaves the outcome unknown -- a 500, a reset connection, a
                # timeout -- is one where the run may already exist and already be
                # paid for. Retrying does not recover the request; it buys the same
                # evaluation twice, and the caller cannot tell, because the first
                # response never arrived.
                #
                # A 429 still waits: that is the server declining to create
                # anything, which is knowledge rather than ambiguity. `retry()`
                # below also keeps its retries -- it is idempotent on the run being
                # retried.
                max_retries=0,
            )
        )

    def retrieve(self, evaluation_id: str) -> Evaluation:
        return Evaluation.model_validate(
            self._t.json(method="GET", path=f"/v1/evaluations/{evaluation_id}")
        )

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        video_id: str | None = None,
        status: Sequence[str] | None = None,
    ) -> EvaluationList:
        """Your evaluations, newest first.

        ``offset`` addresses a page directly, and the response's ``counts`` is
        what tells you when to stop: ``limit`` caps one response at 100, so
        deciding you have reached the end because a page came back short is wrong
        at exactly the boundary where it matters.

        ``status`` is sent comma-joined, which the API accepts.
        """
        return EvaluationList.model_validate(
            self._t.json(
                method="GET",
                path="/v1/evaluations",
                params={
                    "limit": limit,
                    "offset": offset,
                    "video_id": video_id,
                    # An empty sequence means "no filter", not "keep nothing" --
                    # a caller building this from checkboxes hits that.
                    "status": ",".join(status) if status else None,
                },
            )
        )

    def iterate(
        self,
        *,
        page_size: int = 100,
        video_id: str | None = None,
        status: Sequence[str] | None = None,
    ) -> Iterator[Evaluation]:
        """Walk every page, so a caller does not hold the offset arithmetic.

        Stops on ``counts`` rather than on a short page. Yields one evaluation at
        a time: a large account is the case this exists for, and materialising it
        into one list would undo the point.
        """
        limit = min(100, max(1, page_size))
        offset = 0
        while True:
            page = self.list(limit=limit, offset=offset, video_id=video_id, status=status)
            yield from page.data

            # `counts` is a census over the owner and video scope that IGNORES
            # `status`. Summing all of it while filtering would walk past the end
            # of the filtered set, asking for pages that come back empty -- so the
            # statuses asked for are selected out of it.
            #
            # Absent (an older deployment) falls back to the short-page test,
            # which is why that is not the primary rule: it cannot tell a final
            # full page from a penultimate one.
            total = _count_for(page.counts, status) if page.counts else None
            offset += len(page.data)
            if not page.data:
                return
            if total is not None:
                if offset >= total:
                    return
            elif len(page.data) < limit:
                return

    def retry(self, evaluation_id: str) -> Evaluation:
        """Run a failed evaluation again. Returns the NEW evaluation, queued.

        The only idempotent submission in this API, and it is idempotent on the
        run being retried rather than on your request: press it in a burst and
        every caller is handed the same successor. :meth:`create` has no such
        guarantee, so this is the safe way to react to a failure.

        It costs the ordinary price, which is not paying twice -- the failed run
        was refunded when it settled, and whichever detectors did land were
        cached, so only the missing ones are bought again.

        Raises :class:`InvalidRequestError` when there is nothing to retry: the
        run has not finished, it did not fail, it delivered everything asked of
        it, it analyzed no stored clip, it has been attempted too many times, or
        its earlier retry was deleted. The message says which.
        """
        return Evaluation.model_validate(
            self._t.json(method="POST", path=f"/v1/evaluations/{evaluation_id}/retry")
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

    def create_and_wait(
        self,
        *,
        video: Mapping[str, Any],
        prompt: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        glitch_types: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        timeout: float = 600.0,
    ) -> Evaluation:
        """Submit and wait. What most callers want.

        The parameters are SPELLED OUT rather than forwarded as ``**params``, and
        that is the difference between a typed call and an untyped one. This is
        the method every quickstart uses; with ``**params`` an editor could not
        complete it, mypy could not check it, and ``inspect.signature`` reported
        nothing a caller could act on. The mistake was only reported at runtime,
        by ``create()``, one frame further in than where it was made.

        The TypeScript client has always had this — its `params` argument is a
        typed object — so this is also the two clients agreeing.
        """
        queued = self.create(
            video=video,
            prompt=prompt,
            model=model,
            model_version=model_version,
            glitch_types=glitch_types,
            metadata=metadata,
        )
        if queued.status.value in SETTLED:
            return queued
        return self.wait_until_settled(queued.id, timeout=timeout)


def _count_for(counts: EvaluationCounts, status: Sequence[str] | None) -> int:
    """How many evaluations the census covers, restricted to the statuses asked for.

    ``counts`` ignores ``status`` by design: one census answers both "how much is
    there" and "how many pages does this filter have", and the second question is
    this function.

    A status the census does not mention contributes 0 rather than raising -- a
    deployment that adds a status this client has not heard of should not break
    paging for a client that is not asking for it.
    """
    census: dict[str, int] = {
        k: v for k, v in counts.model_dump().items() if isinstance(v, int)
    }
    keys = list(status) if status else list(census)
    return sum(census.get(k, 0) for k in keys)
