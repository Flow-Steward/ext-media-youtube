"""The outcome of a write after it was sent: one decision for every write step.

``write_outcome`` is the only place that decides it, for the generated steps and the
everyday ones alike. Its inputs are the status, the Content-Type, the state of the body
and the step's class; the first rule that applies decides:

- T1. A status that is not a success (not 2xx): decided by the transport before this
  (a refusal in Google's error form, or an unknown outcome).
- T2. The method has a response schema (JSON is promised) and the Content-Type is
  present and not JSON: ``timeout_unknown``, decided by the headers whatever happened
  to the body.
- T3. The body was read, is not empty, JSON is promised, and it does not start with
  ``{`` or ``[`` or does not parse: ``timeout_unknown``. A confirmed write is kept
  despite size, time, depth and budget, never despite a body that is not what the
  source promises.
- T4. The body was not read in full (limit, deadline, broken connection) or nests
  deeper than 48 levels, by the step's class:
  c) ``CREATE`` (the step returns the new resource's id: Upload video, Create
     playlist, Add video to playlist, Reply to comment): ``invalid_response`` +
     ``timeout_unknown``, saying the resource was created but its id is not known;
  d) ``OTHER``: ``ok``, ``succeeded``, ``data: null``, a warning.
  (Class a, the confirmation inside the body, and class b, a batch answered with a
  list per record, do not occur in the YouTube APIs: the status confirms every write,
  and the methods that take several ids answer with no body.)
- T5. The body parsed, but a creation's answer does not carry the new id: as T4c.
- T6. Otherwise success: ``processing``, ``applied``, ``check`` as the method says.

An empty body is not a parsed body: a write of class OTHER takes it as success without
data (T6); a creation without an id is T5.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from . import errors
from .errors import ExtensionError
from .nesting import MAX_ANSWER_DEPTH
from .transport import CHECK, Answer, TooDeep, unknown

OTHER = "other"
CREATE = "create"

_JSON_STARTS = (b"{", b"[")


def json_type(content_type: str) -> bool:
    return content_type == "application/json" or (
        content_type.startswith("application/") and content_type.endswith("+json")
    )


def processing_of(entry: Mapping[str, Any] | None, status: int) -> dict[str, Any]:
    """What YouTube's answer to a write confirms: the change made (completed), or the
    request accepted and processed by YouTube afterwards (accepted: an uploaded video,
    which YouTube processes after the upload)."""
    facts = (entry or {}).get("processing") or {}
    if status == 202 or facts.get("accepted_always"):
        return {
            "processing": "accepted",
            "applied": False,
            "check": {"operation_id": facts.get("check")},
        }
    return {"processing": "completed", "applied": True, "check": None}


def write_outcome(
    context: Any,
    answer: Answer,
    shown: str,
    *,
    entry: Mapping[str, Any] | None,
    promised: bool,
    step: str = OTHER,
    find_id: Callable[[Any], str | None] | None = None,
    what: str = "resource",
) -> dict[str, Any]:
    """The outputs of a write YouTube answered with a success status: ``data``,
    ``warnings``, ``processing``, ``applied``, ``check``; for a creation also ``id``.
    Raises for an unknown outcome (T2, T3, T4c, T5)."""
    status = answer.status
    out: dict[str, Any] = {"data": None, "warnings": []}
    out.update(processing_of(entry, status))
    kind = answer.content_type
    # T2: by the headers, whatever happened to the body.
    if promised and kind and not json_type(kind):
        raise _not_json(shown, status, f"its Content-Type is {errors.safe_text(kind, 60)}")
    missing: str | None = answer.unread
    parsed = False
    if missing is None and not answer.empty:
        start = answer.raw.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
        if promised and start not in _JSON_STARTS:  # T3
            raise _not_json(shown, status, "its body does not start with { or [")
        try:
            out["data"] = context.transport.json(answer)
            parsed = True
        except TooDeep:
            missing = f"it nests deeper than {MAX_ANSWER_DEPTH} levels"
        except ValueError:
            if promised:  # T3
                raise _not_json(shown, status, "its body does not parse") from None
            out["data"] = context.transport.text(answer, 20_000)
            out["warnings"].append(
                f"YouTube confirmed {shown} (HTTP {status}) but its answer is not JSON; it is "
                "returned as text"
            )
    if missing is not None:  # T4
        said = f"YouTube confirmed {shown} (HTTP {status}) but its answer was not read ({missing})"
        if step == CREATE:
            raise _created(shown, status, said, what)
        out["warnings"].append(said + "; it is not returned (data is null)")
        return out
    if step == CREATE:  # T5
        found = find_id(out["data"]) if find_id is not None and parsed else None
        if found is None:
            raise _created(
                shown,
                status,
                f"YouTube confirmed {shown} (HTTP {status}) but its answer does not name the "
                f"new {what}",
                what,
            )
        out["id"] = found
    return out  # T6


def _created(shown: str, status: int, said: str, what: str) -> ExtensionError:
    return ExtensionError(
        errors.INVALID_RESPONSE,
        f"The {what} was created: {said}, so its id is not known; find the {what} in "
        "YouTube before running the step again",
        failure_class="provider",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=status,
    )


def _not_json(shown: str, status: int, why: str) -> ExtensionError:
    return unknown(
        f"YouTube answered {shown} with HTTP {status} but not with the JSON the source "
        f"documents for it ({why})" + CHECK,
        errors.INVALID_RESPONSE,
        status,
    )


def resource_id(value: Any) -> str | None:
    """The ``id`` text of a YouTube resource (a creation's answer), or None."""
    if not isinstance(value, Mapping):
        return None
    ident = value.get("id")
    if isinstance(ident, str) and ident.strip() and len(ident) <= 200:
        return ident.strip()
    return None


__all__ = [
    "CREATE",
    "OTHER",
    "json_type",
    "processing_of",
    "resource_id",
    "write_outcome",
]
