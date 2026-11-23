"""Keep one step's result inside what the host accepts.

The host (core 0.9.23 ``secret_reflection``) walks every value of an extension
response for reflected secrets and fails closed past 3 Mi traversed nodes, nesting
depth 64 or 64 Mi compared code points of distinct strings; it counts no rows or
strings as such. Its default output cap is 5 MiB, and ``main.py`` caps the
serialized response at 4.5 MiB. This module keeps a result inside tighter limits,
with room for the envelope:

- serialized size at most ``MAX_SERIALIZED_BYTES`` (3,500,000 bytes): the main limit;
- at most ``MAX_NODES`` (2,000,000) values and keys;
- containers nested at most ``MAX_DEPTH`` (48) levels below the result object.

It measures exactly what is written: every ``Decimal`` as the text ``results.plain``
writes for it (``numbers.plain``: plain notation inside the bounds), after the token
was removed from the answer (``transport.json``), never as ``str(Decimal)``, whose
exponential form is shorter than what is written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from . import errors, numbers
from .errors import ExtensionError

MAX_NODES = 2_000_000
MAX_DEPTH = 48
MAX_SERIALIZED_BYTES = 3_500_000


@dataclass(frozen=True)
class Totals:
    """What a value costs the host: values and keys, nesting below it, written bytes."""

    nodes: int = 0
    depth: int = 0
    size: int = 0

    def __add__(self, other: Totals) -> Totals:
        return Totals(
            self.nodes + other.nodes, max(self.depth, other.depth), self.size + other.size
        )

    def within(self) -> bool:
        return (
            self.nodes <= MAX_NODES
            and self.depth <= MAX_DEPTH
            and self.size <= MAX_SERIALIZED_BYTES
        )


def measure(value: Any) -> Totals:
    """The cost of ``value``: nodes (values and keys), container depth below it, and the
    bytes it is written as."""
    nodes = deepest = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, level = stack.pop()
        nodes += 1
        if isinstance(node, dict):
            deepest = max(deepest, level)
            nodes += len(node)
            stack.extend((nested, level + 1) for nested in node.values())
        elif isinstance(node, (list, tuple)):
            deepest = max(deepest, level)
            stack.extend((nested, level + 1) for nested in node)
    return Totals(nodes, deepest, written_size(value))


def written_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_written).encode(
            "utf-8"
        )
    )


def _written(item: Any) -> str:
    """What ``results.plain`` writes for a value JSON cannot hold (a ``Decimal``)."""
    return numbers.plain(item) if isinstance(item, Decimal) else str(item)


def too_large() -> ExtensionError:
    return ExtensionError(
        errors.RESPONSE_TOO_LARGE,
        "This YouTube result is too large for one step output. Narrow it with the step's "
        "filters or read fewer records per page.",
        definitely_no_external_effect=True,
        external_effect_status="failed",
    )


def fits(result: Any) -> bool:
    return measure(result).within()


def ensure_fits(result: Any) -> None:
    if not fits(result):
        raise too_large()


__all__ = ["MAX_DEPTH", "Totals", "ensure_fits", "fits", "measure", "too_large", "written_size"]
