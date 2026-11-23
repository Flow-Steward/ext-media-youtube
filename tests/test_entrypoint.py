"""main.py and health.py as the host runs them: a subprocess, JSON in and out."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from support import BUNDLE, TOKEN, payload

import main


def invoke(request: Any) -> tuple[int, dict[str, Any]]:
    code, text = invoke_raw(request)
    return code, json.loads(text)


def invoke_raw(request: Any) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "main.py"],
        cwd=BUNDLE,
        input=json.dumps(request) if not isinstance(request, bytes) else request.decode(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return proc.returncode, proc.stdout


def test_a_test_mode_write_answers_without_network() -> None:
    request = payload("create_playlist", {"title": "Launch"}, test_mode=True)
    code, response = invoke(request)
    assert code == 0, response
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert response["result"]["playlist_id"] is None
    assert TOKEN not in json.dumps(response)


def test_a_test_mode_upload_checks_its_inputs_and_sends_nothing() -> None:
    request = payload("upload_video", {"title": "Clip"}, test_mode=True)
    code, response = invoke(request)
    assert code == 2
    assert response["error_code"] == "invalid_payload"
    assert "file" in response["error"]


def test_an_unknown_operation_is_refused() -> None:
    code, response = invoke(payload("drop_everything"))
    assert code == 2
    assert response["error_code"] == "unsupported_operation"


def test_a_request_that_is_not_json_is_refused() -> None:
    code, response = invoke(b"{not json")
    assert code == 2
    assert response["error_code"] == "invalid_payload"


def test_the_last_resort_answer_keeps_the_facts_of_a_write() -> None:
    huge = {
        "ok": True,
        "result": {"id": "1", "blob": "x" * 6_000_000, "check": {"operation_id": "x"}},
        "external_effect_status": "succeeded",
        "definitely_no_external_effect": False,
    }
    final, _ = main._bounded_serialized_response(huge)
    # A confirmed change stays a success, cut to its short values.
    assert final["ok"] is True and final["error_code"] is None
    assert final["external_effect_status"] == "succeeded"
    assert final["result"]["id"] == "1" and "blob" not in final["result"]
    assert final["result"]["check"] == {"operation_id": "x"}
    assert final["definitely_no_external_effect"] is False


def test_the_last_resort_answer_of_a_read_is_response_too_large() -> None:
    final, _ = main._bounded_serialized_response({"ok": True, "result": {"b": "x" * 6_000_000}})
    assert final["ok"] is False and final["error_code"] == "response_too_large"


def test_control_characters_are_removed_from_the_output() -> None:
    final, _ = main._bounded_serialized_response({"ok": True, "result": {"t": "a\x00b"}})
    assert final["result"]["t"] == "a b" and final["output_sanitized"] is True


def test_health_answers_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, "health.py"], cwd=BUNDLE, capture_output=True, text=True, check=True
    )
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["extension_id"] == "flowsteward.youtube"
    # 81 generated steps, 13 everyday steps and the post-connect action.
    assert report["declared_operations"] == 95
    assert set(report["specification_sha256"]) == {"data"}


def _playlist_request(number: str, *, test_mode: bool = True) -> bytes:
    raw = (
        '{"mode":"action","contract_version":"extension_host_v2","runtime_context":{"test_mode":'
        + ("true" if test_mode else "false")
        + ',"group_id":null,"for_each_id":null,"step_id":"s","step_execution_id":"e"},'
        '"action":{"action_id":"add_video_to_playlist","input":{"connection_ref":"c",'
        '"playlist_id":"PL1","video_id":"v1","position":' + number + '},"target":{"connection":'
        '{"connection_id":"c","connection_type":"youtube_channel","secrets":{"access_token":"'
        + TOKEN
        + '"}}}}}'
    )
    return raw.encode()


@pytest.mark.parametrize(
    "number",
    ["1e1000000", "1e-1000000", "9" * 5000, "1" * 41, "1e31"],
    ids=["1e1000000", "1e-1000000", "int-5000-digits", "int-41-digits", "1e31"],
)
def test_a_number_outside_the_bounds_is_refused_before_anything_is_sent(number: str) -> None:
    for test_mode in (True, False):
        code, text = invoke_raw(_playlist_request(number, test_mode=test_mode))
        # The refusal is small: the number was never written out in full.
        assert len(text) < 2_000, len(text)
        response = json.loads(text)
        assert code == 2
        assert response["error_code"] == "invalid_payload"
        assert response["definitely_no_external_effect"] is True
        assert response["external_effect_status"] == "failed"


def test_a_number_inside_the_bounds_still_reaches_the_step() -> None:
    code, response = invoke(_playlist_request("3"))
    assert code == 0, response
    assert response["definitely_no_external_effect"] is True


def test_a_request_nested_too_deeply_is_refused() -> None:
    deep = "[" * 40 + "]" * 40
    raw = (
        '{"mode":"action","action":{"action_id":"create_playlist","input":{"title":' + deep + "}}}"
    )
    code, response = invoke(raw.encode())
    assert code == 2 and response["error_code"] == "invalid_payload"
    assert "nested deeper" in response["error"]
