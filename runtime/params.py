"""Step inputs checked against the source's parameters and turned into the request.

Each node comes from runtime/registry.json (built from the pinned Discovery document
by tests/reference/build_contracts.py): its kind, whether it is required, its allowed
values and bounds. Numbers stay exact to the wire; nothing goes through float.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from . import numbers
from .errors import invalid


def text(value: Any, what: str, *, max_length: int, min_length: int = 0) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise invalid(f"{what} must be text")
    result = (
        value
        if isinstance(value, str)
        else (numbers.plain(value) if isinstance(value, Decimal) else str(value))
    )
    result = result.strip()
    if not result:
        raise invalid(f"{what} is empty")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in result):
        raise invalid(f"{what} may not contain control characters")
    if len(result) > max_length or len(result) < min_length:
        raise invalid(f"{what} must be {min_length or 1} to {max_length} characters")
    return result


_DATE_TIME_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?)?"
    r"(Z|z|[+-](\d{2}):?(\d{2}))?"
)


def date_time(value: str, what: str) -> str:
    """``value`` when it is a real date (and time), as RFC 3339 writes one; an impossible
    one (2026-02-31, 25:00, an offset past 23:59) is refused, never sent."""
    match = _DATE_TIME_RE.fullmatch(value)
    if match is None:
        raise invalid(f"{what} must be a date and time such as 2026-11-01T00:00:00Z")
    year, month, day, hour, minute, second, _, off_h, off_m = match.groups()
    try:
        date(int(year), int(month), int(day))
        if hour is not None:
            datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second or 0)
            ).replace(
                tzinfo=timezone(timedelta(hours=int(off_h or 0), minutes=int(off_m or 0)))
            ).astimezone(UTC)
    except (ValueError, OverflowError):
        raise invalid(f"{what} is not a real date and time: {value[:40]}") from None
    return value


def wire(value: Any) -> str:
    """A checked value as query text (Decimal plainly, booleans as JSON writes them)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return numbers.plain(value)
    return str(value)


def integer(node: Mapping[str, Any], value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise invalid(f"{what} must be a whole number")
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,19}", value.strip()):
        value = int(value.strip())
    if not isinstance(value, int):
        raise invalid(f"{what} must be a whole number")
    low, high = node.get("minimum"), node.get("maximum")
    if (low is not None and value < low) or (high is not None and value > high):
        raise invalid(f"{what} must be a whole number from {low} to {high}")
    return value


def check(node: Mapping[str, Any], value: Any, what: str) -> Any:
    """One parameter value checked against its node: what to send (a list sends one
    query parameter per item)."""
    kind = node["kind"]
    if kind == "text":
        result = text(
            value,
            what,
            max_length=int(node["max_length"]),
            min_length=int(node.get("min_length") or 0),
        )
        allowed = node.get("allowed")
        if allowed and result not in allowed:
            raise invalid(f"{what} must be one of: {', '.join(allowed)}")
        if node.get("format") == "date-time":
            return date_time(result, what)
        return result
    if kind == "integer":
        return integer(node, value, what)
    if kind == "boolean":
        if not isinstance(value, bool):
            raise invalid(f"{what} must be true or false")
        return value
    if kind == "text_list":
        items = value if isinstance(value, list) else [value]
        limit = int(node["max_items"])
        if not items or len(items) > limit:
            raise invalid(f"{what} must be a list of 1 to {limit} values")
        out = [
            text(item, f"{what} item {i}", max_length=int(node["item_max_length"]))
            for i, item in enumerate(items, 1)
        ]
        allowed = node.get("allowed")
        if allowed and any(item not in allowed for item in out):
            raise invalid(f"{what} values must be among: {', '.join(allowed)}")
        return out
    raise invalid(f"{what} has a kind this extension does not know")  # pragma: no cover


__all__ = ["check", "date_time", "integer", "text", "wire"]
