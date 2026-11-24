"""Shaping a step's result: the write markers and the output budget."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from . import budget, errors, numbers


def mark_write(result: dict[str, Any]) -> dict[str, Any]:
    result["external_effect_status"] = "succeeded"
    result["definitely_no_external_effect"] = False
    return result


def nothing_sent(result: dict[str, Any]) -> dict[str, Any]:
    """A write step that finished without sending anything that can change data (the
    transport never sent a change): the pair the host takes for "no external effect",
    as in a test run; nothing was accepted or applied."""
    result.update(processing=None, applied=False, check=None)
    result["external_effect_status"] = "failed"
    result["definitely_no_external_effect"] = True
    return result


#: Field names that identify a record and are kept when its full echo cannot be.
_IDENTIFYING = re.compile(r"^(id|code|number|status)$|(_id|Id|ID|_code|_no|Number)$")
_SCALARS = (str, int, Decimal, bool, type(None))
MAX_KEPT_TEXT = 200
MAX_KEPT_WARNINGS = 20


def _identifiers(record: Mapping[str, Any]) -> dict[str, Any]:
    """The record's own identifying fields (short scalars only)."""
    return {
        key: value
        for key, value in record.items()
        if isinstance(key, str)
        and _IDENTIFYING.search(key)
        and isinstance(value, _SCALARS)
        and len(str(value)) <= MAX_KEPT_TEXT
    }


def _short_scalars(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key != "warnings" and isinstance(value, _SCALARS) and len(str(value)) <= MAX_KEPT_TEXT
    }


MAX_KEPT_ITEMS = 100
#: Kept whole however the result is cut: where to read the outcome of the write.
KEPT_WHOLE = ("check",)


def _cut_list(items: list[Any]) -> tuple[list[Any], str]:
    """A list cut for the output, and what the warning says about it: records cut to
    their identifying fields, short scalars (ids, codes) kept as they are, other items
    left out; at most ``MAX_KEPT_ITEMS``."""
    kept: list[Any] = []
    records = 0
    for item in items:
        if isinstance(item, Mapping):
            kept.append(_identifiers(item))
            records += 1
        elif isinstance(item, _SCALARS) and len(str(item)) <= MAX_KEPT_TEXT:
            kept.append(item)
        if len(kept) >= MAX_KEPT_ITEMS:
            break
    if not kept:
        return [], "it is left out"
    said = f"{len(kept)} of its {len(items)} items are kept"
    if records:
        said += ", records cut to their identifying fields (id, code, numbers)"
    return kept, said


def fit_write_result(result: dict[str, Any]) -> dict[str, Any]:
    """The result of a write that already happened, cut until it fits the step output.

    Every large record or list is cut to its identifying fields (id, code, numbers),
    largest first. What is left is checked; when even that
    does not fit, only the result's short values and the first warnings are kept. A cut
    is always said in the warnings; the write's own facts are set by the caller.
    """
    if budget.fits(result):
        return result
    warnings = result.setdefault("warnings", [])
    large = [
        key
        for key, value in result.items()
        if key not in {"warnings", *KEPT_WHOLE} and isinstance(value, (Mapping, list))
    ]
    large.sort(key=lambda k: budget.measure(result[k]).size, reverse=True)
    for key in large:
        value = result[key]
        if isinstance(value, Mapping):
            result[key] = _identifiers(value)
            said = "only its identifying fields (id, code, numbers) are kept"
        else:
            result[key], said = _cut_list(value)
        warnings.append(
            f"The {key} returned is too large for the step output; {said}: see it in YouTube"
        )
        if budget.fits(result):
            return result
    kept = _short_scalars(result)
    for key in KEPT_WHOLE:
        if isinstance(result.get(key), Mapping):
            kept[key] = dict(result[key])
    kept["warnings"] = [
        errors.safe_text(w, errors.TEXT_LIMIT) for w in warnings[:MAX_KEPT_WARNINGS]
    ] + ["The result is cut to its identifiers: it is too large for the step output"]
    return kept


def plain(value: Any) -> Any:
    """Decimals as plain text, so no number goes through float on the way out; one outside
    ``numbers``' bounds in its own exponential notation, never expanded."""
    if isinstance(value, Decimal):
        return numbers.plain(value)
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def ok(result: Mapping[str, Any]) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "result": plain(dict(result)),
        "error_code": None,
        "error": None,
        "errors": [],
    }
    if "external_effect_status" in result:
        response["external_effect_status"] = result["external_effect_status"]
        response["definitely_no_external_effect"] = result["definitely_no_external_effect"]
    return response
