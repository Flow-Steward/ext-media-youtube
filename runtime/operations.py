"""Run one workflow step against YouTube: the entry point."""

from __future__ import annotations

import sys
import traceback
from collections.abc import Mapping
from typing import Any

from flowsteward_extension_sdk import stream_artifact_bytes, write_artifact_stream

from . import budget, catalog, composites, errors, generic
from .connection import connection_from_payload
from .context import ArtifactReader, ArtifactWriter, Context, TransportFactory
from .errors import ExtensionError, error_response, invalid
from .files import ARTIFACT_TIMEOUT_SECONDS
from .limits import STEP_MARGIN_SECONDS, STEP_TIMEOUT_SECONDS
from .results import fit_write_result, mark_write, nothing_sent, ok
from .transport import DeadlineReached, YouTubeTransport


def handle_runtime(
    payload: Mapping[str, Any],
    *,
    transport_factory: TransportFactory = YouTubeTransport,
    artifact_reader: ArtifactReader = stream_artifact_bytes,
    artifact_writer: ArtifactWriter = write_artifact_stream,
) -> dict[str, Any]:
    """Dispatch one invocation through the closed registry."""
    transport: YouTubeTransport | None = None
    try:
        operation_id, raw_input = _envelope(payload)
        if operation_id not in catalog.OPERATION_IDS:
            raise errors.no_effect(
                errors.UNSUPPORTED_OPERATION, "That operation is not part of this extension"
            )
        operation_input = _as_input(raw_input)
        effect = operation_id in catalog.EFFECT_OPERATION_IDS
        if effect and _test_mode(payload):
            # The host suppresses test-mode effects before spawning the extension;
            # this is the backstop. Validated first, then nothing is sent or taken.
            return ok(neutral_result(operation_id, operation_input))
        connection_ref = operation_input.get("connection_ref")
        connection = connection_from_payload(
            payload, connection_ref=connection_ref if isinstance(connection_ref, str) else ""
        )
        transport = transport_factory(connection)
        # A step that saves a file keeps the file's own time in reserve, so a take never
        # starts when what it takes could not be saved in time.
        reserve = ARTIFACT_TIMEOUT_SECONDS if operation_id in catalog.FILE_OUTPUT_IDS else 0.0
        transport.deadline = (
            transport.clock() + STEP_TIMEOUT_SECONDS - STEP_MARGIN_SECONDS - reserve
        )
        context = Context(
            payload=payload,
            operation_input=operation_input,
            transport=transport,
            artifact_reader=artifact_reader,
            artifact_writer=artifact_writer,
        )
        if effect:
            # Inputs are checked in full before anything is sent.
            validate(operation_id, operation_input)
        if operation_id in catalog.COMPOSITE_IDS:
            result = composites.COMPOSITES[operation_id](context)
        else:
            result = generic.run(context, operation_id)
        if effect and not transport.mutated:
            # Nothing that can change data was sent: the same pair as a test run, not
            # a write that succeeded.
            return ok(nothing_sent(fit_write_result(result)))
        if effect:
            return ok(mark_write(fit_write_result(result)))
        budget.ensure_fits(result)
        return ok(result)
    except DeadlineReached:
        if transport is not None and transport.mutated:
            return error_response(
                errors.TIMEOUT_UNKNOWN,
                "The step ran out of time after a change was sent to YouTube; check it before "
                "running the step again",
            )
        made = transport.calls if transport is not None else 0
        return error_response(
            errors.TIMEOUT,
            f"The step ran out of time after {made} requests to YouTube; nothing was changed"
            if made
            else "The step ran out of time before YouTube could be called",
            retry_facts={"definitely_no_external_effect": True, "external_effect_status": "failed"},
        )
    except ExtensionError as exc:
        _mark_unsent(exc, transport)
        if (
            transport is not None
            and transport.committed
            and exc.definitely_no_external_effect is not False
        ):
            # Backstop: once YouTube confirmed a change in this step, no later
            # failure may report "nothing changed".
            exc = ExtensionError(
                exc.code if exc.code != errors.INVALID_PAYLOAD else errors.INTERNAL_ERROR,
                f"{exc.message}. YouTube already confirmed a change in this step; check it "
                "before running the step again.",
                failure_class="provider",
                retryable=False,
                definitely_no_external_effect=False,
                external_effect_status="timeout_unknown",
                http_status=exc.http_status,
            )
        return error_response(exc.code, exc.message, retry_facts=exc.retry_facts())
    except Exception as exc:
        where = _where(exc)
        # A safe trace for the operator: the exception's type and place, never its text
        # (which could hold data or the key), on stderr for the host's logs.
        print(f"flowsteward.youtube internal error: {where}", file=sys.stderr)
        response = error_response(
            errors.INTERNAL_ERROR, f"The operation could not be completed ({where})"
        )
        if transport is None or not transport.mutated:
            response["definitely_no_external_effect"] = True
            response["external_effect_status"] = "failed"
        else:
            response["definitely_no_external_effect"] = False
            response["external_effect_status"] = "timeout_unknown"
        return response


def _where(exc: BaseException) -> str:
    """``TypeError at runtime/documents.py:123 in totals`` — no values."""
    frames = traceback.extract_tb(exc.__traceback__)
    inside = [f for f in frames if "/runtime/" in f.filename.replace("\\", "/")]
    chosen = inside or list(frames)
    if not chosen:
        return type(exc).__name__
    frame = chosen[-1]
    path = frame.filename.replace("\\", "/")
    path = path[path.rfind("/runtime/") + 1 :] if "/runtime/" in path else path.rsplit("/", 1)[-1]
    return f"{type(exc).__name__} at {path}:{frame.lineno} in {frame.name}"


def _mark_unsent(exc: ExtensionError, transport: YouTubeTransport | None) -> None:
    """A failure before any change could be sent cannot have had an effect."""
    if transport is not None and transport.mutated:
        return
    if exc.definitely_no_external_effect is None:
        exc.definitely_no_external_effect = True
    if exc.definitely_no_external_effect and exc.external_effect_status is None:
        exc.external_effect_status = "failed"


_ALLOWED_ACTION_KEYS = frozenset(
    {"action_id", "operation_id", "page_id", "component_id", "context", "input", "target"}
)


def _envelope(payload: Mapping[str, Any]) -> tuple[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("mode") != "action":
        raise invalid("Request mode must be action")
    action = payload.get("action")
    if not isinstance(action, Mapping) or set(action) - _ALLOWED_ACTION_KEYS:
        raise invalid("The action envelope is invalid")
    operation_id = action.get("action_id") or action.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise invalid("An operation id is required")
    return operation_id.strip(), action.get("input")


def _as_input(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise invalid("The operation input must be an object")
    return {str(k): v for k, v in raw.items() if v is not None and v != ""}


def _test_mode(payload: Mapping[str, Any]) -> bool:
    context = payload.get("runtime_context")
    if not isinstance(context, Mapping):
        return False
    value = context.get("test_mode", False)
    if not isinstance(value, bool):
        raise invalid("runtime_context.test_mode must be boolean")
    return value


def validate(operation_id: str, operation_input: Mapping[str, Any]) -> None:
    """Check a write's inputs without calling YouTube."""
    if operation_id in composites.VALIDATORS:
        composites.VALIDATORS[operation_id](operation_input)
    else:
        generic.prepare(operation_id, operation_input)


def neutral_result(operation_id: str, operation_input: Mapping[str, Any]) -> dict[str, Any]:
    """Every declared output of a write in a test run: inputs checked, nothing sent."""
    validate(operation_id, operation_input)
    if operation_id in composites.NEUTRAL:
        result: dict[str, Any] = dict(composites.NEUTRAL[operation_id])
    else:
        result = {"status": None, "data": None, "etag": None}
    # Nothing was sent, so nothing was accepted or applied.
    result.update(processing=None, applied=False, check=None)
    result["warnings"] = ["Test run: the inputs were checked and nothing was sent to YouTube"]
    # "failed" + definitely-no-effect is the pair Core accepts for "no external effect
    # happened"; an extension may not report "suppressed".
    result["external_effect_status"] = "failed"
    result["definitely_no_external_effect"] = True
    return result
