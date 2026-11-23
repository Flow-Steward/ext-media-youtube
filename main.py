#!/usr/bin/env python3
"""YouTube subprocess entrypoint."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from dispatcher import dispatch_runtime
from runtime import nesting, numbers

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SERIALIZED_RESPONSE_BYTES = 9 * 512 * 1024
_CONTROL_TRANSLATION = {
    codepoint: " " for codepoint in (*range(32), *range(127, 160)) if codepoint not in {9, 10, 13}
}


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        response = _refused("The request exceeds its safe limit")
    else:
        try:
            payload = _load_payload(raw)
        except UnboundedNumber as exc:
            response = _refused(str(exc))
        except (TooDeep, RecursionError):
            response = _refused(TOO_DEEP)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _refused("The request is not valid JSON")
        else:
            response = dispatch_runtime(payload)
    final_response, serialized = _bounded_serialized_response(response)
    sys.stdout.buffer.write(serialized)
    sys.stdout.buffer.write(b"\n")
    return 0 if final_response.get("ok") is True else 2


class UnboundedNumber(ValueError):
    """A number of the request is outside what this extension writes out in full."""


class TooDeep(ValueError):
    """The request nests deeper than ``nesting.MAX_REQUEST_DEPTH``."""


TOO_DEEP = f"The request is nested deeper than {nesting.MAX_REQUEST_DEPTH} levels; nothing was sent"


def _float(text: str) -> Decimal:
    number = numbers.read(text, integer=False)
    if not isinstance(number, Decimal):
        raise UnboundedNumber(
            f"The request has a number with more than {numbers.MAX_DIGITS} digits or an "
            f"exponent outside {numbers.MIN_EXPONENT}..{numbers.MAX_EXPONENT}; nothing was sent"
        )
    return number


def _int(text: str) -> int:
    number = numbers.read(text, integer=True)
    if not isinstance(number, int):
        raise UnboundedNumber(
            f"The request has a whole number with more than {numbers.MAX_DIGITS} digits; "
            "nothing was sent"
        )
    return number


def _constant(text: str) -> Any:
    raise UnboundedNumber(f"The request has {text[:20]}, which is not a JSON number")


def _load_payload(raw: bytes) -> dict[str, Any]:
    """The request, with every number that has a point read as ``Decimal``.

    1234567890.12345678 reaches the checks as written, not rounded through float.
    Nothing in the host's envelope is used as a float, so the whole request is
    read the same way. A number outside ``runtime.numbers``' bounds (digits and
    exponent, from ``Decimal.as_tuple()``) refuses the request before it is used,
    so ``1e1000000`` is never written out in full. A request nested deeper than
    ``nesting.MAX_REQUEST_DEPTH`` is refused before it is parsed.
    """
    text = raw.decode("utf-8")
    if not text.strip():
        return {}
    # Counted on the bytes before parsing: the JSON reader recurses per level.
    if nesting.too_deep(raw, nesting.MAX_REQUEST_DEPTH):
        raise TooDeep(TOO_DEEP)
    payload = json.loads(text, parse_float=_float, parse_int=_int, parse_constant=_constant)
    return payload if isinstance(payload, dict) else {}


def _refused(message: str) -> dict[str, Any]:
    """A request refused before anything was read or sent."""
    response = _error_response("invalid_payload", message)
    response["definitely_no_external_effect"] = True
    response["external_effect_status"] = "failed"
    return response


def _bounded_serialized_response(response: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    sanitized, changed = _sanitize_json_value(dict(response))
    if not isinstance(sanitized, dict):
        raise TypeError("extension response must be an object")
    if changed:
        sanitized["output_sanitized"] = True
    serialized = _json_bytes(sanitized)
    if len(serialized) + 1 <= MAX_SERIALIZED_RESPONSE_BYTES:
        return sanitized, serialized
    return _too_large(sanitized)


#: What the last-resort answer keeps of a response that is too large.
MAX_KEPT_TEXT = 200
MAX_KEPT_FIELDS = 50
MAX_KEPT_WARNINGS = 5
KEPT_WHOLE = ("check",)
CUT_TO_IDENTIFIERS = (
    "The change was saved, but its full result is too large for the step output; only its "
    "identifiers and short values are kept: see the rest in YouTube"
)


def _too_large(response: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    """The last-resort answer when the response does not fit the output.

    A change YouTube confirmed stays a success (``ok`` true, ``succeeded``): the host
    turns a failed answer that claims ``succeeded`` into an unknown outcome, and the
    change was made. Its result is cut to its short values (identifiers, status,
    processing) with a warning that says so. Any other response becomes
    ``response_too_large`` with its effect facts kept.
    """
    status = response.get("external_effect_status")
    result = response.get("result")
    kept = _short_values(result) if isinstance(result, Mapping) else {}
    if status == "succeeded":
        warnings = result.get("warnings") if isinstance(result, Mapping) else None
        kept["warnings"] = [
            str(w)[:MAX_KEPT_TEXT] for w in (warnings or [])[:MAX_KEPT_WARNINGS]
        ] + [CUT_TO_IDENTIFIERS]
        final = {
            "ok": True,
            "result": kept,
            "error_code": None,
            "error": None,
            "errors": [],
            "external_effect_status": "succeeded",
            "definitely_no_external_effect": False,
        }
        return final, _json_bytes(final)
    message = "The extension response exceeds its safe output limit"
    if status == "timeout_unknown":
        message += "; a change may have been saved, check it before running the step again"
    error_response = _error_response("response_too_large", message)
    for key in ("external_effect_status", "definitely_no_external_effect"):
        if key in response:
            error_response[key] = response[key]
    if isinstance(result, Mapping):
        error_response["result"] = {**kept, "warnings": []}
    return error_response, _json_bytes(error_response)


def _short_values(result: Mapping[str, Any]) -> dict[str, Any]:
    """The result's short scalar values, and those one level down in an object (such as
    ``check``); at most ``MAX_KEPT_FIELDS`` each."""

    def short(value: Mapping[str, Any]) -> dict[str, Any]:
        out = {
            key: item
            for key, item in list(value.items())[: MAX_KEPT_FIELDS * 4]
            if isinstance(key, str)
            and len(key) <= MAX_KEPT_TEXT
            and isinstance(item, (str, int, float, bool, type(None)))
            and len(str(item)) <= MAX_KEPT_TEXT
        }
        return dict(list(out.items())[:MAX_KEPT_FIELDS])

    kept = short(result)
    for key, item in list(result.items())[: MAX_KEPT_FIELDS * 4]:
        if key == "warnings" or not isinstance(key, str) or len(key) > MAX_KEPT_TEXT:
            continue
        if key in KEPT_WHOLE and isinstance(item, Mapping):
            # Where to read the write's outcome: kept as it is (bounded by the runtime).
            kept[key] = {k: v for k, v in item.items() if isinstance(v, (str, type(None)))}
        elif isinstance(item, Mapping) and len(kept) < MAX_KEPT_FIELDS:
            kept[key] = short(item)
    return kept


def _sanitize_json_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        sanitized = value.translate(_CONTROL_TRANSLATION)
        return sanitized, sanitized != value
    if isinstance(value, Mapping):
        mapped: dict[Any, Any] = {}
        changed = False
        for key, item in value.items():
            sanitized, item_changed = _sanitize_json_value(item)
            mapped[key] = sanitized
            changed = changed or item_changed
        return mapped, changed
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[Any] = []
        changed = False
        for item in value:
            sanitized, item_changed = _sanitize_json_value(item)
            items.append(sanitized)
            changed = changed or item_changed
        return items, changed
    return value, False


def _json_bytes(response: Mapping[str, Any]) -> bytes:
    return json.dumps(
        response,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _error_response(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "result": {"warnings": []},
        "error_code": code,
        "error": message,
        "errors": [{"code": code, "message": message}],
        "warnings": [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
