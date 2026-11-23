"""YouTube's resumable upload: a workflow file sent in parts to an upload session.

The pinned Discovery document lists, for each method that takes a file, the protocols
``simple`` and ``resumable`` with the upload path (``mediaUpload.protocols``), the
media types it accepts and its maximum size. This module sends the file with the
resumable protocol to the ``simple`` path with ``uploadType=resumable``, as the Google
API client does:

1. The method's own HTTP method on the upload path, with ``uploadType=resumable``, the
   step's query, the metadata (the ``body`` input) as JSON and the headers
   ``X-Upload-Content-Type`` and ``X-Upload-Content-Length``. YouTube answers with the
   session address in ``Location``.
2. ``PUT`` of the file to that address in parts of ``CHUNK_BYTES`` (a multiple of
   256 KiB, as the protocol requires of every part but the last), each with
   ``Content-Range: bytes first-last/total``. YouTube answers HTTP 308 with ``Range:
   bytes=0-n`` (the bytes it kept) while bytes are missing, and 200 or 201 with the
   resource after the last byte.

YouTube creates the resource only with the last byte, so opening the session and the
parts before the last cannot change anything: they are sent and checked like reads
(a failure there means nothing was created). The part that carries the last byte is a
write. The session address authorizes uploads to it, so it is treated as a secret: it
never reaches a result, a warning, an error or a log line.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from urllib.parse import parse_qsl, urlsplit

from . import errors
from .context import Context
from .errors import ExtensionError
from .transport import Answer, Call, DeadlineReached

#: Size of every part but the last: 8 MiB, a multiple of 256 KiB.
CHUNK_BYTES = 8 * 1024 * 1024
#: Parts that may come back without progress before the upload is given up.
MAX_STALLS = 3
_RANGE = re.compile(r"^bytes=0-(\d{1,15})$")


def _no_effect(message: str) -> ExtensionError:
    return errors.no_effect(
        errors.TIMEOUT if "time" in message else errors.UPSTREAM_FAILURE,
        message,
        failure_class="provider",
        retryable=False,
    )


def kept(answer: Answer) -> int:
    """How many bytes YouTube kept, from the ``Range`` of an HTTP 308 answer (none: 0)."""
    value = answer.headers.get("Range")
    if value is None:
        return 0
    match = _RANGE.fullmatch(value.strip())
    if match is None:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            "YouTube answered an upload part with a Range that is not bytes=0-n; nothing was "
            "created",
            failure_class="provider",
            retryable=False,
        )
    return int(match.group(1)) + 1


def resumable(
    context: Context,
    *,
    method: str,
    upload_path: str,
    api: str,
    shown: str,
    query: Sequence[tuple[str, str]],
    metadata: bytes | None,
    content: bytes,
    content_type: str,
) -> Answer:
    """Upload ``content``; YouTube's answer to the last part (the created resource)."""
    transport = context.transport
    total = len(content)
    start = Call(
        method=method,
        path=upload_path,
        shown=shown,
        api=api,
        query=(("uploadType", "resumable"), *query),
        headers={
            "X-Upload-Content-Type": content_type,
            "X-Upload-Content-Length": str(total),
        },
        body=metadata if metadata is not None else b"",
        content_type="application/json; charset=UTF-8",
        success=("200", "201"),
    )
    try:
        opened = transport.prepare_upload(start)
    except DeadlineReached:
        raise _no_effect("The step ran out of time before the upload could start") from None
    session = opened.headers.get("Location")
    if not session:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"YouTube opened no upload session for {shown} (no Location); nothing was created",
            failure_class="provider",
            retryable=False,
        )
    transport.add_secret(session)
    for name, value in parse_qsl(urlsplit(session).query):
        if name == "upload_id" and len(value) >= 16:
            transport.add_secret(value)
    offset = 0
    stalls = 0
    while True:
        end = min(offset + CHUNK_BYTES, total)
        last = end == total
        part = Call(
            method="PUT",
            path=upload_path,
            shown=shown,
            api=api,
            headers={"Content-Range": f"bytes {offset}-{end - 1}/{total}"},
            body=content[offset:end],
            content_type=content_type,
            success=("200", "201", "308"),
            session_url=session,
        )
        if last:
            try:
                answer = transport.write_unconfirmed(part)
            except DeadlineReached:
                # Raised before the last part was sent.
                raise _no_effect(
                    f"The step ran out of time after {offset} of {total} bytes were uploaded; "
                    "YouTube creates nothing before the last byte, so nothing was created. "
                    "Run the step again with more time or a smaller file"
                ) from None
        else:
            try:
                answer = transport.prepare_upload(part)
            except DeadlineReached:
                raise _no_effect(
                    f"The step ran out of time after {offset} of {total} bytes were uploaded; "
                    "YouTube creates nothing before the last byte, so nothing was created. "
                    "Run the step again with more time or a smaller file"
                ) from None
            except ExtensionError as exc:
                raise errors.no_effect(
                    exc.code,
                    f"The upload stopped after {offset} of {total} bytes: {exc.message}. "
                    "YouTube creates nothing before the last byte, so nothing was created",
                    failure_class=exc.failure_class,
                    retryable=False,
                    http_status=exc.http_status,
                ) from None
        if answer.status != 308:
            transport.committed = True
            return answer
        progress = kept(answer)
        if progress > end or progress < 0:
            raise _bad_progress(progress, total, last)
        if progress <= offset:
            stalls += 1
            if stalls >= MAX_STALLS:
                raise _bad_progress(progress, total, last)
        else:
            stalls = 0
        offset = progress


def _bad_progress(progress: int, total: int, last: bool) -> ExtensionError:
    message = (
        f"YouTube kept {progress} of {total} bytes and did not take more; the upload is not "
        "complete"
    )
    if last:
        return ExtensionError(
            errors.INVALID_RESPONSE,
            message + "; check in YouTube whether the resource exists before running the step "
            "again",
            failure_class="provider",
            retryable=False,
            definitely_no_external_effect=False,
            external_effect_status="timeout_unknown",
        )
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        message + "; nothing was created",
        failure_class="provider",
        retryable=False,
    )


__all__ = ["CHUNK_BYTES", "kept", "resumable"]
