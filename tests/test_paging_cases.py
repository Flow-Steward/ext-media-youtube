"""One set of paging cases, the same in YouTube and in YouTube Analytics.

Both extensions read lists with ``runtime/pages.py``'s ``collect``. The cases below are
copied unchanged into both repositories; ``PINNED_SHA256`` is the SHA-256 of their
canonical JSON and is the same constant in both, so a case changed in one repository
and not in the other fails this test there.

A case gives the pages a list answers (by the token that asks for them; ``null`` asks
for the first page), how the step is started and what it must return.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from runtime import pages
from runtime.errors import ExtensionError

CASES: list[dict[str, Any]] = [
    {
        "name": "reads to the end",
        "pages": {"": [["a", "b"], "T2"], "T2": [["c"], None]},
        "most": 10,
        "expect": {"items": ["a", "b", "c"], "complete": True, "token": None, "skip": None},
    },
    {
        "name": "a page crossing the maximum is cut",
        "pages": {"": [["a", "b"], "T2"], "T2": [["c", "d"], "T3"]},
        "most": 3,
        "expect": {"items": ["a", "b", "c"], "complete": False, "token": "T2", "skip": 1},
    },
    {
        "name": "the next run leaves out what was returned",
        "pages": {"T2": [["c", "d"], "T3"], "T3": [["e"], None]},
        "start": "T2",
        "skip": 1,
        "most": 10,
        "expect": {"items": ["d", "e"], "complete": True, "token": None, "skip": None},
    },
    {
        "name": "the maximum on a page end continues on the next page",
        "pages": {"": [["a", "b"], "T2"]},
        "most": 2,
        "expect": {"items": ["a", "b"], "complete": False, "token": "T2", "skip": 0},
    },
    {
        "name": "the first page cut continues without a token",
        "pages": {"": [["a", "b"], "T2"]},
        "most": 1,
        "expect": {"items": ["a"], "complete": False, "token": None, "skip": 1},
    },
    {
        "name": "skip on the first page",
        "pages": {"": [["a", "b"], None]},
        "skip": 1,
        "most": 10,
        "expect": {"items": ["b"], "complete": True, "token": None, "skip": None},
    },
    {
        "name": "an empty page with a token does not end the list",
        "pages": {"": [[], "T2"], "T2": [["a"], None]},
        "most": 10,
        "expect": {"items": ["a"], "complete": True, "token": None, "skip": None},
    },
    {
        "name": "a record seen twice is returned once",
        "pages": {"": [["a", "b"], "T2"], "T2": [["b", "c"], None]},
        "most": 10,
        "expect": {"items": ["a", "b", "c"], "complete": True, "token": None, "skip": None},
    },
    {
        "name": "a token sent twice is an incomplete read",
        "pages": {"": [["a"], "T2"], "T2": [["b"], "T2"]},
        "most": 10,
        "error": "invalid_response",
    },
    {
        "name": "a skip larger than the page is refused",
        "pages": {"T2": [["a"], None]},
        "start": "T2",
        "skip": 5,
        "most": 10,
        "error": "invalid_payload",
    },
]

#: SHA-256 of ``canonical(CASES)``; the same constant in both repositories.
PINNED_SHA256 = "c659fe1c6682740dfb3e19c0a4fd4613f66fd50b23f35af2453936f495124e8d"


def canonical(cases: list[dict[str, Any]]) -> bytes:
    return json.dumps(cases, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_the_cases_are_the_ones_both_extensions_pin() -> None:
    assert hashlib.sha256(canonical(CASES)).hexdigest() == PINNED_SHA256


def _context() -> Any:
    transport = SimpleNamespace(calls=0, remaining=lambda: 10_000.0)
    return SimpleNamespace(transport=transport)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_paging_case(case: dict[str, Any]) -> None:
    context = _context()
    asked: list[str | None] = []

    def fetch(token: str | None, limit: int) -> Any:
        context.transport.calls += 1
        asked.append(token)
        records, following = case["pages"][token or ""]
        answer: dict[str, Any] = {"items": [{"id": r} for r in records]}
        if following is not None:
            answer["nextPageToken"] = following
        return answer

    def collect() -> dict[str, Any]:
        return pages.collect(
            context,
            fetch=fetch,
            shown="GET /list",
            start=case.get("start"),
            page_size=50,
            smallest=1,
            most=case["most"],
            to_file=False,
            out_key="items",
            skip=case.get("skip", 0),
        )

    if "error" in case:
        with pytest.raises(ExtensionError) as caught:
            collect()
        assert caught.value.code == case["error"]
        return
    out = collect()
    expect = case["expect"]
    assert [i["id"] for i in out["items"]] == expect["items"]
    assert len(out["items"]) <= case["most"]
    assert out["count"] == len(expect["items"])
    assert out["complete"] is expect["complete"]
    assert out["next_page_token"] == expect["token"]
    assert out["next_skip"] == expect["skip"]
