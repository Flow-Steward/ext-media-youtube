"""How deeply a JSON text nests, counted on its raw bytes before it is parsed.

Python's JSON reader recurses once per ``[`` or ``{``; a text nested a few thousand
levels deep makes it raise ``RecursionError`` instead of a JSON error, and every
later walk over the value (token removal, the output budget, the host's secret
check, which stops at depth 64) has the same limit. So the depth is counted first,
on the bytes, with brackets inside strings ignored:

- a request deeper than ``MAX_REQUEST_DEPTH`` is refused before anything is read;
- a YouTube answer deeper than ``MAX_ANSWER_DEPTH`` is not read: a read fails with
  ``invalid_response``, a confirmed write keeps its facts without the answer.
"""

from __future__ import annotations

import re
from itertools import accumulate

MAX_REQUEST_DEPTH = 32
MAX_ANSWER_DEPTH = 48

#: A JSON string with its escapes; an unterminated one runs to the end of the text, as
#: it does for the JSON reader. The closing quote is optional, so a match never fails
#: and never backtracks: the scan is linear whatever the text.
_STRING = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"?', re.DOTALL)
_NOT_BRACKETS = bytes(b for b in range(256) if b not in b"[]{}")
_STEP = {ord("["): 1, ord("{"): 1, ord("]"): -1, ord("}"): -1}


def depth(raw: bytes) -> int:
    """The deepest bracket nesting of ``raw``, brackets inside JSON strings ignored."""
    brackets = _STRING.sub(b"", raw).translate(None, _NOT_BRACKETS)
    if not brackets:
        return 0
    return max(0, max(accumulate(map(_STEP.__getitem__, brackets))))


def too_deep(raw: bytes, limit: int) -> bool:
    return depth(raw) > limit


__all__ = ["MAX_ANSWER_DEPTH", "MAX_REQUEST_DEPTH", "depth", "too_deep"]
