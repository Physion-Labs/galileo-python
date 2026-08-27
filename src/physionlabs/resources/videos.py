"""Upload a video once, then reference it from as many evaluations as you like.

Three calls, and :meth:`Videos.upload` makes all three so a caller does not have
to know that. Ask where to put the file, send it, say it has landed -- then wait
for validation, because a video is not usable until it has been checked.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .._poll import poll_until
from .._transport import Transport
from ..errors import InvalidRequestError
from ..models import Video, VideoReservation

SETTLED = frozenset({"ready", "failed"})

#: Kept in step with the contract's ``VideoCreate.size_bytes`` maximum.
MAX_FILE_BYTES = 52_428_800

_CHUNK = 1024 * 1024


class Videos:
    def __init__(self, transport: Transport, upload_base_url: str) -> None:
        self._t = transport
        self._upload_base_url = upload_base_url.rstrip("/")

    def retrieve(self, video_id: str) -> Video:
        return Video.model_validate(self._t.json(method="GET", path=f"/v1/videos/{video_id}"))

    def wait_until_ready(self, video_id: str, *, timeout: float = 600.0) -> Video:
        """Poll until validation finishes.

        ``failed`` is a normal outcome, not an exception: the file was rejected,
        and that is an answer.
        """
        return poll_until(
            lambda: self.retrieve(video_id),
            lambda v: v.status.value in SETTLED,
            describe=f"video {video_id}",
            status_of=lambda v: v.status.value,
            timeout=timeout,
        )

    def upload(
        self,
        path: str | Path,
        *,
        dedupe: bool = True,
        wait: bool = True,
        timeout: float = 600.0,
    ) -> Video:
        """Upload a local MP4 and return the record, ready to reference.

        The bytes are STREAMED, never held in memory: a 50 MB clip costs a 1 MB
        buffer, and neither does the hash pass. That matters more than it sounds --
        a caller uploading a directory of clips from a thread pool would otherwise
        hold all of them at once.

        ``dedupe`` hashes the file first so the server can skip the transfer when
        it already holds this exact content. One extra streamed pass, cheap next
        to sending it, and the difference between re-uploading a clip you already
        sent and not.
        """
        file = Path(path)
        size = file.stat().st_size

        # Refused here rather than by the server: the caller learns before spending
        # the upload, and learns which file it was.
        if size > MAX_FILE_BYTES:
            raise InvalidRequestError(
                status=413,
                type="invalid_request_error",
                code="file_too_large",
                message=f"{file.name} is {size} bytes; the limit is {MAX_FILE_BYTES}.",
            )
        if size == 0:
            raise InvalidRequestError(
                status=400,
                type="invalid_request_error",
                code="invalid_request",
                message=f"{file.name} is empty.",
            )

        body: dict[str, object] = {"content_type": "video/mp4", "size_bytes": size}
        if dedupe:
            body["content_hash"] = _hash_file(file)

        # 1. Ask where to put it.
        reserved = VideoReservation.model_validate(
            self._t.json(method="POST", path="/v1/videos", body=body)
        )

        # The server already held this content: nothing to send, nothing to wait for.
        if reserved.skip_upload or not reserved.upload_path:
            return self.retrieve(reserved.video_id)

        # 2. Send the bytes -- to storage, NOT to the API. No Authorization
        #    header: that host never needed the key, and a key sent to a host that
        #    did not need it is a key disclosed.
        with file.open("rb") as fh:
            self._t.send(
                method="PUT",
                absolute_url=_absolute(reserved.upload_path, self._upload_base_url),
                content=fh,
                content_type="video/mp4",
                content_length=size,
                anonymous=True,
                # Re-sending tens of megabytes on a transient failure is not free,
                # and the grant behind `upload_path` expires -- a retry past that
                # point fails on the signature rather than the network. A streamed
                # body cannot be replayed anyway.
                max_retries=0,
            )

        # 3. Say it has landed, which starts validation.
        done = Video.model_validate(
            self._t.json(method="POST", path=f"/v1/videos/{reserved.video_id}/complete")
        )
        if not wait or done.status.value in SETTLED:
            return done
        return self.wait_until_ready(reserved.video_id, timeout=timeout)


def _hash_file(file: Path) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with file.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(upload_path: str, base: str) -> str:
    """``upload_path`` may be a path or a full URL; only the former needs a root."""
    if upload_path.startswith(("http://", "https://")):
        return upload_path
    sep = "" if upload_path.startswith("/") else "/"
    return f"{base}{sep}{upload_path}"
