"""The generated steps: inputs checked from the source, requests, answers and lists."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl

import pytest
from support import TOKEN, Artifacts, FakeYouTube, ok, raw, refuse, run, text_of

from runtime import budget, generic

REGISTRY = generic.registry()


def minimal_input(entry: dict[str, Any]) -> dict[str, Any]:
    """The smallest valid input of a generated step."""
    given: dict[str, Any] = {}
    for prm in entry["path_params"]:
        given[prm["input"]] = "x1"
    for prm in entry["query"]:
        n = prm["node"]
        if not n["required"]:
            continue
        if n["kind"] == "text_list":
            given[prm["input"]] = [n["allowed"][0]] if n.get("allowed") else ["snippet"]
        elif n["kind"] == "integer":
            given[prm["input"]] = n.get("minimum", 1)
        elif n["kind"] == "boolean":
            given[prm["input"]] = True
        elif n.get("allowed"):
            given[prm["input"]] = n["allowed"][-1]
        elif n.get("format") == "date":
            given[prm["input"]] = "2026-01-01"
        elif n.get("format") == "date-time":
            given[prm["input"]] = "2026-01-01T00:00:00Z"
        else:
            given[prm["input"]] = "x1"
    body = entry["body"]
    if body and body["required"]:
        given["body"] = {body["json"]["properties"][0]: "x"}
    if body and body["upload"] and body["upload"]["required"]:
        given["file"] = "art"
    return given


@pytest.mark.parametrize("operation_id", sorted(REGISTRY))
def test_every_generated_step_accepts_its_minimal_input(operation_id: str) -> None:
    entry = REGISTRY[operation_id]
    plan = generic.prepare(operation_id, minimal_input(entry))
    assert plan.method == entry["method"]
    assert "{" not in plan.path


@pytest.mark.parametrize("operation_id", sorted(REGISTRY))
def test_every_generated_step_refuses_unknown_inputs(operation_id: str) -> None:
    given = {**minimal_input(REGISTRY[operation_id]), "nonsense_field": 1}
    result = run(operation_id, given, FakeYouTube())
    assert result["error_code"] == "invalid_payload"
    assert "nonsense_field" in result["error"]
    assert result["definitely_no_external_effect"] is True


def test_repeated_parameters_send_one_value_each() -> None:
    fake = FakeYouTube(ok({"items": []}))
    run("get_videos", {"part": ["snippet", "statistics"], "id": ["a", "b"]}, fake)
    assert fake.calls[0].query == [
        ("part", "snippet"),
        ("part", "statistics"),
        ("id", "a"),
        ("id", "b"),
    ]


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ({"part": ["snippet"], "max_results": 51}, "from 1 to 50"),
        ({"part": ["snippet"], "max_results": "x"}, "whole number"),
        ({"part": ["snippet"], "chart": "trending"}, "must be one of"),
        ({"part": ["snippet"], "my_rating": "none", "id": "a\x00b"}, "control characters"),
        ({"part": []}, "part is required"),
        ({}, "part is required"),
    ],
)
def test_query_values_are_checked_against_the_source(given: dict[str, Any], message: str) -> None:
    fake = FakeYouTube()
    result = run("get_videos", given, fake)
    assert result["error_code"] == "invalid_payload", result
    assert message in result["error"]
    assert fake.calls == []


@pytest.mark.parametrize("value", ["2026-02-31T00:00:00Z", "2026-01-01T25:00:00Z", "yesterday"])
def test_an_impossible_date_time_is_refused(value: str) -> None:
    result = run("search_youtube", {"part": ["snippet"], "published_after": value}, FakeYouTube())
    assert result["error_code"] == "invalid_payload"


def test_a_body_with_fields_the_resource_does_not_have_is_refused() -> None:
    fake = FakeYouTube()
    result = run(
        "update_playlist", {"part": ["snippet"], "body": {"id": "PL1", "colour": "red"}}, fake
    )
    assert result["error_code"] == "invalid_payload"
    assert "colour" in result["error"] and "Playlist" in result["error"]
    assert fake.calls == []


def test_a_required_body_is_required() -> None:
    result = run("update_playlist", {"part": ["snippet"]}, FakeYouTube())
    assert result["error_code"] == "invalid_payload" and "body is required" in result["error"]


def test_the_body_is_sent_as_json() -> None:
    fake = FakeYouTube(ok({"id": "PL1"}))
    run(
        "update_playlist",
        {"part": ["snippet"], "body": {"id": "PL1", "snippet": {"title": "T"}}},
        fake,
    )
    call = fake.calls[0]
    assert call.verb == "PUT" and call.body == {"id": "PL1", "snippet": {"title": "T"}}
    assert call.headers["content-type"] == "application/json"


def test_a_path_parameter_is_one_encoded_segment() -> None:
    artifacts = Artifacts()
    fake = FakeYouTube(raw(200, b"1\n00:00:01,000 --> 00:00:02,000\nhi\n", "text/plain"))
    result = run("download_caption_track", {"id": "a/b c"}, fake, artifacts=artifacts)
    assert result["ok"] is True, result
    assert fake.calls[0].path == "/youtube/v3/captions/a%2Fb%20c"
    assert ("alt", "media") in fake.calls[0].query


def test_a_downloaded_caption_is_a_workflow_file_without_the_token() -> None:
    artifacts = Artifacts()
    body = f"WEBVTT\n\nhello {TOKEN}\n".encode()
    fake = FakeYouTube(raw(200, body, "text/vtt"))
    result = run("download_caption_track", {"id": "c1", "tfmt": "vtt"}, fake, artifacts=artifacts)
    out = result["result"]
    assert out["file"] == "artifact-1" and out["content_type"] == "text/vtt"
    saved = artifacts.saved[0]
    assert TOKEN.encode() not in saved["data"] and b"[redacted]" in saved["data"]
    assert saved["binding_key"] == "youtube_file"


def test_a_write_without_response_answers_with_no_data() -> None:
    fake = FakeYouTube(raw(204, b""))
    result = run("delete_playlist", {"id": "PL1"}, fake)
    assert result["ok"] is True and result["result"]["data"] is None
    assert result["result"]["processing"] == "completed"
    assert fake.calls[0].verb == "DELETE"


# -- lists ---------------------------------------------------------------------------------


def page(ids: list[str], token: str | None = None, **extra: Any) -> Any:
    body: dict[str, Any] = {"kind": "x#list", "items": [{"id": i} for i in ids], **extra}
    if token:
        body["nextPageToken"] = token
    return ok(body)


def test_one_page_returns_items_and_where_to_continue() -> None:
    fake = FakeYouTube(page(["a", "b"], "T2", pageInfo={"totalResults": 4}))
    result = run("get_playlists", {"part": ["snippet"], "mine": True}, fake)
    out = result["result"]
    assert out["items"] == [{"id": "a"}, {"id": "b"}] and out["count"] == 2
    assert out["complete"] is False and out["next_page_token"] == "T2"
    assert out["data"] == {"kind": "x#list", "pageInfo": {"totalResults": 4}}


def test_all_pages_follows_the_tokens_to_the_end() -> None:
    fake = FakeYouTube(page(["a"], "T2"), page(["b"], "T3"), page(["c"]))
    result = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)
    out = result["result"]
    assert [i["id"] for i in out["items"]] == ["a", "b", "c"]
    assert out["complete"] is True and out["next_page_token"] is None
    assert [dict(c.query).get("pageToken") for c in fake.calls] == [None, "T2", "T3"]
    assert all(dict(c.query)["maxResults"] == "50" for c in fake.calls)


def test_max_items_needs_all_pages() -> None:
    result = run("get_playlists", {"part": ["snippet"], "max_items": 5}, FakeYouTube())
    assert result["error_code"] == "invalid_payload"


def test_all_pages_never_returns_more_than_max_items() -> None:
    fake = FakeYouTube(page(["a", "b"], "T2"), page(["c", "d"], "T3"))
    given = {"part": ["snippet"], "mine": True, "all_pages": True, "max_items": 3, "max_results": 2}
    out = run("get_playlists", given, fake)["result"]
    # The second page is asked for the one record left; YouTube answering more is cut.
    assert dict(fake.calls[1].query)["maxResults"] == "1"
    assert [i["id"] for i in out["items"]] == ["a", "b", "c"]
    assert out["complete"] is False
    assert out["next_page_token"] == "T2" and out["next_skip"] == 1


def test_all_pages_starts_from_the_page_token_given() -> None:
    fake = FakeYouTube(page(["c"]))
    run(
        "get_playlists",
        {"part": ["snippet"], "mine": True, "all_pages": True, "page_token": "T3"},
        fake,
    )
    assert dict(fake.calls[0].query)["pageToken"] == "T3"


def test_an_empty_page_with_a_next_token_does_not_end_the_list() -> None:
    fake = FakeYouTube(page([], "T2"), page(["a"]))
    out = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)[
        "result"
    ]
    assert out["complete"] is True and out["count"] == 1 and len(fake.calls) == 2


def test_a_token_sent_twice_is_an_incomplete_read() -> None:
    fake = FakeYouTube(page(["a"], "T2"), page(["b"], "T2"))
    result = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)
    assert result["error_code"] == "invalid_response"
    assert "not complete" in result["error"]


def test_duplicates_are_returned_once_with_a_warning() -> None:
    fake = FakeYouTube(page(["a", "b"], "T2"), page(["b", "c"]))
    out = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)[
        "result"
    ]
    assert [i["id"] for i in out["items"]] == ["a", "b", "c"]
    assert "appeared twice" in out["warnings"][0]


def test_a_failure_after_the_first_page_returns_what_was_read() -> None:
    fake = FakeYouTube(page(["a"], "T2"), refuse(503, b""))
    out = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)
    assert out["ok"] is True
    result = out["result"]
    assert result["count"] == 1 and result["complete"] is False
    assert result["next_page_token"] == "T2"
    assert "page_token T2" in result["warnings"][-1]


def test_a_failure_on_the_first_page_fails_the_step() -> None:
    fake = FakeYouTube(refuse(503, b""))
    result = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)
    assert result["ok"] is False and result["error_code"] == "upstream_failure"


def test_a_full_output_stops_with_the_token_of_the_page_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(budget, "MAX_SERIALIZED_BYTES", 5000)
    big = "x" * 1200
    fake = FakeYouTube(
        ok({"items": [{"id": "a", "t": big}], "nextPageToken": "T2"}),
        ok({"items": [{"id": "b", "t": big}], "nextPageToken": "T3"}),
        ok({"items": [{"id": "c", "t": big}], "nextPageToken": "T4"}),
    )
    result = run("get_playlists", {"part": ["snippet"], "mine": True, "all_pages": True}, fake)
    assert result["ok"] is True, result
    out = result["result"]
    assert [i["id"] for i in out["items"]] == ["a", "b"]
    assert out["complete"] is False and out["next_page_token"] == "T3"
    assert budget.fits(out)


def test_a_first_page_that_does_not_fit_is_asked_with_half_the_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(budget, "MAX_SERIALIZED_BYTES", 5000)
    big = "x" * 1200
    fake = FakeYouTube(
        ok({"items": [{"id": i, "t": big} for i in "abcd"], "nextPageToken": "T2"}),
        ok({"items": [{"id": i, "t": big} for i in "ab"], "nextPageToken": "T2"}),
        ok({"items": [{"id": "c", "t": big}, {"id": "d", "t": big}], "nextPageToken": "T3"}),
    )
    given = {"part": ["snippet"], "mine": True, "all_pages": True, "max_results": 4}
    out = run("get_playlists", given, fake)["result"]
    assert [dict(c.query)["maxResults"] for c in fake.calls] == ["4", "2", "2"]
    # The page asked with a token keeps the size the token was issued for.
    assert [i["id"] for i in out["items"]] == ["a", "b"]
    assert out["next_page_token"] == "T2"


@pytest.mark.parametrize("operation_id", sorted(k for k, v in REGISTRY.items() if v["pager"]))
def test_every_list_step_offers_all_pages(operation_id: str) -> None:
    names = generic.inputs_of(REGISTRY[operation_id])
    assert {"all_pages", "max_items", "page_token"} <= names


def test_a_live_chat_is_read_one_page_at_a_time() -> None:
    entry = REGISTRY["get_live_chat_messages"]
    assert entry["pager"] is None
    assert "page_token" in generic.inputs_of(entry)


def test_a_read_returns_no_token_in_its_output() -> None:
    fake = FakeYouTube(page(["a"], extra=TOKEN))
    result = run("get_playlists", {"part": ["snippet"], "mine": True}, fake)
    assert TOKEN not in text_of(result)


def test_query_strings_are_url_encoded() -> None:
    fake = FakeYouTube(ok({"items": []}))
    run("search_youtube", {"part": ["snippet"], "q": "a&b=c"}, fake)
    assert ("q", "a&b=c") in parse_qsl(fake.calls[0].url.split("?", 1)[1])


def test_an_empty_download_is_an_invalid_answer_not_a_missing_file() -> None:
    artifacts = Artifacts()
    fake = FakeYouTube(raw(200, b"", "text/vtt"))
    result = run("download_caption_track", {"id": "c1"}, fake, artifacts=artifacts)
    assert result["ok"] is False, result
    assert result["error_code"] == "invalid_response"
    assert result["definitely_no_external_effect"] is True
    assert artifacts.saved == []


def test_every_file_step_is_covered_by_the_empty_download_rule() -> None:
    assert [k for k, v in generic.registry().items() if v["answer"] == "file"] == [
        "download_caption_track"
    ]
