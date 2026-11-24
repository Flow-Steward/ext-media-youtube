"""Workflow files: what an upload step sends and what a download step saves.

An uploaded file is streamed with the SDK's ``stream_artifact_bytes`` in parts of
``READ_CHUNK_BYTES`` into a temporary file on disk, which the upload then sends part by
part (runtime/upload.py): the process holds about one part in memory, never the whole
file. The SDK checks the file's SHA-256 when the stream ends, before the upload starts. Flow Steward
caps a workflow file a step reads at ``FS_EXTENSION_ARTIFACT_MAX_BYTES`` (209,715,200
bytes, 200 MiB, unless the host sets another value; contracts/artifact_policies.yaml
declares it with ``max_size_env``). YouTube's own maximum per method (``maxSize`` in the
pinned Discovery document; for a video 274,877,906,944 bytes, 256 GiB) is larger for
videos, so a video above the host's cap cannot be uploaded from a workflow file.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from typing import BinaryIO

from . import errors
from .context import Context
from .errors import ExtensionError

ARTIFACT_TIMEOUT_SECONDS = 120.0
#: The least time left in which a workflow file is still read (our decision).
MIN_READ_WINDOW_SECONDS = 5
#: Size of each piece read from Flow Steward storage: the SDK's default chunk, 1 MiB.
READ_CHUNK_BYTES = errors.MIB
#: The host's default cap of a workflow file (FS_EXTENSION_ARTIFACT_MAX_BYTES).
HOST_ARTIFACT_MAX_BYTES = 200 * errors.MIB
MAX_DOWNLOAD_BYTES = 40 * errors.MIB

#: Must match contracts/artifact_policies.yaml (tests/reference/build_contracts.py).
UPLOAD_BINDING = "youtube_upload"
DOWNLOAD_BINDING = "youtube_file"


def host_cap() -> int:
    """The host's cap of a workflow file, as the host sets it for this process."""
    raw = os.environ.get("FS_EXTENSION_ARTIFACT_MAX_BYTES", "")
    try:
        value = int(raw)
    except ValueError:
        return HOST_ARTIFACT_MAX_BYTES
    return value if value > 0 else HOST_ARTIFACT_MAX_BYTES


def spool(
    context: Context, handle: object, *, max_bytes: int, what: str = "The file"
) -> tuple[BinaryIO, int]:
    """A workflow file given as an input, copied to a temporary file (deleted when it is
    closed), and its size; nothing is sent when it fails. The caller closes it."""
    if not isinstance(handle, str) or not handle.strip():
        raise errors.invalid(f"{what} must be a workflow file from an earlier step")
    remaining = context.transport.remaining()
    if remaining < MIN_READ_WINDOW_SECONDS:
        raise errors.no_effect(errors.TIMEOUT, "The step ran out of time before the file was read")
    limit = min(max_bytes, host_cap())
    sink = tempfile.TemporaryFile()  # noqa: SIM115 - handed to the caller, closed there
    total = 0
    try:
        for chunk in context.artifact_reader(
            dict(context.payload),
            artifact_id=handle.strip(),
            chunk_size=READ_CHUNK_BYTES,
            timeout_seconds=min(ARTIFACT_TIMEOUT_SECONDS, remaining),
        ):
            total += len(chunk)
            if total > limit:
                raise errors.invalid(
                    f"{what} is larger than the {errors.size_text(limit)} this step uploads"
                )
            sink.write(chunk)
    except ExtensionError:
        sink.close()
        raise
    except Exception:
        sink.close()
        raise errors.no_effect(
            errors.ARTIFACT_INPUT_UNAVAILABLE, f"{what} could not be read from Flow Steward storage"
        ) from None
    if total == 0:
        sink.close()
        raise errors.no_effect(errors.ARTIFACT_INPUT_UNAVAILABLE, f"{what} is empty")
    sink.seek(0)
    return sink, total


def save(context: Context, data: bytes, *, content_type: str, what: str) -> str:
    """Save ``data`` as a workflow file; its handle."""
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise errors.no_effect(
            errors.RESPONSE_TOO_LARGE,
            f"{what} is larger than {errors.size_text(MAX_DOWNLOAD_BYTES)}",
        )
    try:
        written = context.artifact_writer(
            dict(context.payload),
            [data],
            binding_key=DOWNLOAD_BINDING,
            content_type=content_type,
            timeout_seconds=ARTIFACT_TIMEOUT_SECONDS,
        )
    except ExtensionError:
        raise
    except Exception:
        raise errors.no_effect(
            errors.ARTIFACT_OUTPUT_UNAVAILABLE, f"{what} could not be saved"
        ) from None
    handle = written.get("artifact_handle") if isinstance(written, Mapping) else None
    if not isinstance(handle, str) or not handle.strip():
        raise errors.no_effect(errors.ARTIFACT_OUTPUT_UNAVAILABLE, f"{what} could not be saved")
    return handle.strip()


__all__ = [
    "ARTIFACT_TIMEOUT_SECONDS",
    "DOWNLOAD_BINDING",
    "HOST_ARTIFACT_MAX_BYTES",
    "MAX_DOWNLOAD_BYTES",
    "UPLOAD_BINDING",
    "host_cap",
    "spool",
    "save",
]
