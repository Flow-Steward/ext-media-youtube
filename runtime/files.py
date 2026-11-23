"""Workflow files: what an upload step sends and what a download step saves.

An uploaded file is read whole with the SDK's ``read_artifact_bytes``. Flow Steward
caps a workflow file a step reads at ``FS_EXTENSION_ARTIFACT_MAX_BYTES`` (209,715,200
bytes, 200 MiB, unless the host sets another value; contracts/artifact_policies.yaml
declares it with ``max_size_env``). YouTube's own maximum per method (``maxSize`` in the
pinned Discovery document; for a video 274,877,906,944 bytes, 256 GiB) is larger for
videos, so a video above the host's cap cannot be uploaded from a workflow file.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from . import errors
from .context import Context
from .errors import ExtensionError

ARTIFACT_TIMEOUT_SECONDS = 120.0
#: The host's default cap of a workflow file (FS_EXTENSION_ARTIFACT_MAX_BYTES).
HOST_ARTIFACT_MAX_BYTES = 200 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024

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


def _size(count: int) -> str:
    if count % (1024 * 1024 * 1024) == 0:
        return f"{count // (1024 * 1024 * 1024)} GiB"
    if count % (1024 * 1024) == 0:
        return f"{count // (1024 * 1024)} MiB"
    return f"{count} bytes"


def read(context: Context, handle: object, *, max_bytes: int, what: str = "The file") -> bytes:
    """The bytes of a workflow file given as an input; nothing is sent when it fails."""
    if not isinstance(handle, str) or not handle.strip():
        raise errors.invalid(f"{what} must be a workflow file from an earlier step")
    remaining = context.transport.remaining()
    if remaining < 5:
        raise errors.no_effect(errors.TIMEOUT, "The step ran out of time before the file was read")
    try:
        body = context.artifact_reader(
            dict(context.payload),
            artifact_id=handle.strip(),
            timeout_seconds=min(ARTIFACT_TIMEOUT_SECONDS, remaining),
        )
    except ExtensionError:
        raise
    except Exception:
        raise errors.no_effect(
            errors.ARTIFACT_INPUT_UNAVAILABLE, f"{what} could not be read from Flow Steward storage"
        ) from None
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise errors.no_effect(errors.ARTIFACT_INPUT_UNAVAILABLE, f"{what} is empty")
    limit = min(max_bytes, host_cap())
    if len(body) > limit:
        raise errors.invalid(
            f"{what} is {len(body)} bytes, larger than the {_size(limit)} this step uploads"
        )
    return bytes(body)


def save(context: Context, data: bytes, *, content_type: str, what: str) -> str:
    """Save ``data`` as a workflow file; its handle."""
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise errors.no_effect(errors.RESPONSE_TOO_LARGE, f"{what} is larger than 40 MiB")
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
    "read",
    "save",
]
