"""Table T: the outcome of every write after YouTube answered it with a success status.

The matrix runs three steps (a generated write whose method promises JSON, one whose
method has no response, and an everyday creation that needs the new id) against three
Content-Types and seven states of the body. The expected cell is written out here, not
derived from runtime/outcome.py.
"""

from __future__ import annotations

import json
from email.message import Message
from typing import Any

import pytest
from support import JSON, FakeYouTube, Response, run

from runtime import outcome

STEPS = {
    # step id -> (input, promises JSON, class)
    "update_playlist": (
        {"part": ["snippet"], "body": {"id": "PL9", "snippet": {"title": "T"}}},
        True,
        "other",
    ),
    "delete_playlist": ({"id": "PL9"}, False, "other"),
    "create_playlist": ({"title": "New"}, True, "create"),
}
TYPES = {"json": JSON, "html": "text/html; charset=UTF-8", "none": None}
STATES = ["empty", "parsed", "not_json", "broken_json", "deep", "too_large", "cut_off"]


class CutOff(Response):
    """An answer whose connection breaks after the first part of the body."""

    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        super().__init__(200, body, headers)
        self.reads = 0

    def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if self.reads > 1:
            raise ConnectionResetError("reset")
        return b'{"id": "PL9", "snippet": {'


def answer(state: str, content_type: str | None) -> Response:
    headers = {"Content-Type": content_type} if content_type else {}
    bodies = {
        "empty": b"",
        "parsed": json.dumps({"id": "PL9", "snippet": {"title": "T"}}).encode(),
        "not_json": b"hello",
        "broken_json": b'{"id": "PL9", ',
        "deep": b'{"id": "PL9", "x": ' + b"[" * 49 + b"]" * 49 + b"}",
        "too_large": b'{"id": "PL9", "x": "' + b"y" * 5000 + b'"}',
    }
    response = CutOff(b"", headers) if state == "cut_off" else Response(200, bodies[state], headers)
    if not headers:
        response.headers = Message()
    return response


def expected(step: str, kind: str, state: str) -> str:
    """unknown | success | success_text | success_unread | created"""
    _, promised, klass = STEPS[step]
    if promised and kind == "html":
        return "unknown"  # T2
    if state in {"deep", "too_large", "cut_off"}:
        return "unknown" if klass == "create" else "success_unread"  # T4
    if promised and state in {"not_json", "broken_json"}:
        return "unknown"  # T3
    if state in {"not_json", "broken_json"}:
        return "success_text"  # T6, no JSON promised
    if klass == "create":
        return "created" if state == "parsed" else "unknown"  # T5
    return "success"


CELLS = [(s, k, st) for s in STEPS for k in TYPES for st in STATES]


@pytest.mark.parametrize(("step", "kind", "state"), CELLS)
def test_the_outcome_of_a_write_follows_table_t(
    step: str, kind: str, state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from runtime import generic

    if state == "too_large":
        monkeypatch.setattr(generic, "MAX_ANSWER_BYTES", 1000)
    given, _, _ = STEPS[step]
    fake = FakeYouTube(answer(state, TYPES[kind]))
    result = run(step, given, fake)
    want = expected(step, kind, state)
    assert len(fake.calls) == 1
    if want == "unknown":
        assert result["ok"] is False, result
        assert result["error_code"] == "invalid_response"
        assert result["external_effect_status"] == "timeout_unknown"
        assert result["definitely_no_external_effect"] is False
        return
    assert result["ok"] is True, result
    assert result["external_effect_status"] == "succeeded"
    out = result["result"]
    assert out["processing"] == "completed" and out["applied"] is True
    if want == "success_unread":
        assert out["data"] is None
        assert any("not read" in w for w in out["warnings"])
    elif want == "success_text":
        assert isinstance(out["data"], str)
        assert any("not JSON" in w for w in out["warnings"])
    elif want == "created":
        assert out["playlist_id"] == "PL9"
    elif state == "parsed":
        assert out["data"]["id"] == "PL9"
    else:
        assert out["data"] is None


def test_every_write_goes_through_the_one_function(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = outcome.write_outcome

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(args[2])
        return real(*args, **kwargs)

    monkeypatch.setattr(outcome, "write_outcome", spy)
    run("update_playlist", STEPS["update_playlist"][0], FakeYouTube(answer("parsed", JSON)))
    run("create_playlist", {"title": "New"}, FakeYouTube(answer("parsed", JSON)))
    assert calls == ["PUT /youtube/v3/playlists", "POST /youtube/v3/playlists"]


def test_a_creation_whose_answer_names_no_id_says_it_was_created() -> None:
    body = Response(200, b'{"snippet": {}}', {"Content-Type": JSON})
    result = run("create_playlist", {"title": "New"}, FakeYouTube(body))
    assert result["external_effect_status"] == "timeout_unknown"
    assert "playlist was created" in result["error"]
    assert "find the playlist in YouTube" in result["error"]
