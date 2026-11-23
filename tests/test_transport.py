"""The transport: the token, the hosts, the outcome of refusals, timeouts and limits."""

from __future__ import annotations

import socket
from decimal import Decimal
from email.message import Message
from typing import Any

import pytest
from flowsteward_extension_sdk import PinnedPeerError
from support import (
    JSON,
    TOKEN,
    FakeYouTube,
    google_error,
    ok,
    raw,
    refuse,
    run,
    text_of,
)

from runtime import transport
from runtime.connection import connection_from_payload
from runtime.transport import dumps_json

WRITE = "update_playlist"  # PUT /youtube/v3/playlists, answers a Playlist
WRITE_INPUT = {"part": ["snippet"], "body": {"id": "PL1", "snippet": {"title": "New"}}}
READ = "get_channels"
READ_INPUT = {"part": ["snippet"], "mine": True}


def test_the_token_travels_only_in_the_authorization_header() -> None:
    fake = FakeYouTube(ok({"items": [{"id": "UC1", "snippet": {"title": "T"}}]}))
    result = run("test_connection", {}, fake)
    assert result["ok"] is True
    call = fake.calls[0]
    assert call.headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in call.url
    assert call.host == "youtube.googleapis.com" and call.path == "/youtube/v3/channels"
    assert call.headers["accept"] == "application/json"
    assert TOKEN not in text_of(result)


def test_the_token_is_removed_from_answers_and_refusals() -> None:
    fake = FakeYouTube(ok({"items": [], "echo": f"Bearer {TOKEN}", TOKEN: "key"}))
    result = run(READ, READ_INPUT, fake)
    assert TOKEN not in text_of(result) and "[redacted]" in text_of(result)
    fake = FakeYouTube(refuse(401, google_error(401, "authError", f"token {TOKEN} expired")))
    result = run(READ, READ_INPUT, fake)
    assert result["error_code"] == "authentication_failed"
    assert TOKEN not in text_of(result)


@pytest.mark.parametrize(
    "connection",
    [
        {
            "connection_id": "conn-1",
            "connection_type": "allegro",
            "secrets": {"access_token": TOKEN},
        },
        {"connection_id": "conn-1", "connection_type": "youtube_channel", "secrets": {}},
        {
            "connection_id": "conn-1",
            "connection_type": "youtube_channel",
            "secrets": {"access_token": "short"},
        },
        {
            "connection_id": "conn-1",
            "connection_type": "youtube_channel",
            "secrets": {"access_token": TOKEN, "refresh_token": "r" * 20},
        },
        {
            "connection_id": "other",
            "connection_type": "youtube_channel",
            "secrets": {"access_token": TOKEN},
        },
    ],
)
def test_an_unusable_connection_is_refused_before_any_request(connection: dict[str, Any]) -> None:
    fake = FakeYouTube()
    result = run("test_connection", {}, fake, connection=connection)
    assert result["error_code"] == "invalid_connection"
    assert result["definitely_no_external_effect"] is True
    assert fake.calls == []
    assert TOKEN not in text_of(result)


@pytest.mark.parametrize(
    "connection_type", ["youtube_channel", "youtube_channel_monetized", "youtube_content_owner"]
)
def test_every_connection_type_reaches_the_same_hosts(connection_type: str) -> None:
    fake = FakeYouTube(ok({"items": [{"id": "UC1"}]}))
    result = run("test_connection", {}, fake, connection_type=connection_type)
    assert result["ok"] is True
    assert result["result"]["connection_type"] == connection_type
    assert fake.calls[0].host == "youtube.googleapis.com"


def test_the_connection_never_shows_its_token() -> None:
    from support import payload

    connection = connection_from_payload(payload("x"), connection_ref="conn-1")
    assert TOKEN not in repr(connection) and TOKEN not in str(connection)


# -- outcome of refusals -------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 412])
def test_a_refusal_in_googles_error_form_changed_nothing(status: int) -> None:
    fake = FakeYouTube(refuse(status, google_error(status, "invalidValue", "Bad playlist")))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["ok"] is False
    assert result["definitely_no_external_effect"] is True
    assert result["external_effect_status"] == "failed"
    assert "nothing was changed" in result["error"] and "Bad playlist" in result["error"]
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html>proxy</html>",
        b'{"message": "x"}',
        b"[]",
        # Google's form, but for another status than the one answered.
        b'{"error": {"code": 500, "message": "x"}}',
        b'{"error": {"code": "400", "message": "x"}}',
    ],
)
def test_a_4xx_without_googles_error_form_leaves_the_write_unknown(body: bytes) -> None:
    fake = FakeYouTube(refuse(400, body))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["external_effect_status"] == "timeout_unknown"
    assert result["definitely_no_external_effect"] is False
    assert "check in YouTube" in result["error"]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_server_error_leaves_the_write_unknown(status: int) -> None:
    fake = FakeYouTube(refuse(status, google_error(status, "backendError")))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["external_effect_status"] == "timeout_unknown"
    assert result["definitely_no_external_effect"] is False
    assert result["retryable"] is False
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "reason", ["quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"]
)
def test_a_quota_refusal_is_a_rate_limit_and_changed_nothing(reason: str) -> None:
    fake = FakeYouTube(refuse(403, google_error(403, reason, "The request cannot be completed")))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["error_code"] == "rate_limited"
    assert result["definitely_no_external_effect"] is True
    assert reason in result["error"]


def test_a_used_up_daily_quota_says_so() -> None:
    fake = FakeYouTube(refuse(403, google_error(403, "quotaExceeded", "quota")))
    result = run(READ, READ_INPUT, fake)
    assert "quota is used up" in result["error"]


def test_a_missing_scope_is_an_authentication_failure_that_names_the_connection_type() -> None:
    fake = FakeYouTube(refuse(403, google_error(403, "insufficientPermissions", "Insufficient")))
    result = run(READ, READ_INPUT, fake)
    assert result["error_code"] == "authentication_failed"
    assert "scope" in result["error"]


def test_rate_limit_on_a_write_changed_nothing_and_is_not_retried() -> None:
    fake = FakeYouTube(refuse(429, b"", Retry_After="30"))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["error_code"] == "rate_limited"
    assert result["definitely_no_external_effect"] is True
    assert result["retryable"] is False
    assert "wait 30 s" in result["error"]
    assert len(fake.calls) == 1


def test_rate_limit_on_a_read_is_retryable_after_the_wait_youtube_asks_for() -> None:
    fake = FakeYouTube(refuse(429, b"", Retry_After="12"))
    result = run(READ, READ_INPUT, fake)
    assert result["error_code"] == "rate_limited"
    assert result["retryable"] is True and result["retry_after_seconds"] == 12
    assert len(fake.calls) == 1


def test_a_redirect_is_not_followed() -> None:
    fake = FakeYouTube(refuse(302, b"", Location="https://evil.example"))
    result = run(READ, READ_INPUT, fake)
    assert result["error_code"] == "redirect_rejected"
    assert len(fake.calls) == 1


def test_a_3xx_answer_is_never_a_success_outside_an_upload() -> None:
    fake = FakeYouTube(refuse(308, b"", Range="bytes=0-10"))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["ok"] is False and result["error_code"] == "redirect_rejected"


# -- transport failures and time -------------------------------------------------------------


def test_a_write_timeout_is_unknown_and_sent_once() -> None:
    fake = FakeYouTube(TimeoutError())
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["error_code"] == "timeout_unknown"
    assert result["external_effect_status"] == "timeout_unknown"
    assert result["definitely_no_external_effect"] is False
    assert len(fake.calls) == 1


def test_a_broken_connection_after_a_write_is_unknown() -> None:
    fake = FakeYouTube(ConnectionResetError())
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["external_effect_status"] == "timeout_unknown"


def test_a_read_timeout_changed_nothing() -> None:
    fake = FakeYouTube(TimeoutError())
    result = run(READ, READ_INPUT, fake)
    assert result["error_code"] == "timeout" and result["definitely_no_external_effect"] is True


@pytest.mark.parametrize(
    "message", ["cannot be resolved", "pinned address '10.0.0.1' is not allowed"]
)
def test_dns_and_private_addresses_fail_before_sending(message: str) -> None:
    fake = FakeYouTube(PinnedPeerError(f"YouTube: {message}"))
    result = run(WRITE, WRITE_INPUT, fake)
    assert result["definitely_no_external_effect"] is True


class SlowBody:
    """An answer whose body arrives slower than the step's time allows."""

    def __init__(self, clock: list[float]) -> None:
        self.clock = clock
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = JSON

    def read(self, size: int = -1) -> bytes:
        self.clock[0] += 400
        return b'{"a": 1}'

    def __enter__(self) -> SlowBody:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_a_write_confirmed_by_its_status_keeps_its_facts_when_its_body_is_late() -> None:
    now = [0.0]
    fake = FakeYouTube(SlowBody(now))
    result = run(WRITE, WRITE_INPUT, fake, clock=lambda: now[0])
    assert result["ok"] is True, result
    assert result["external_effect_status"] == "succeeded"
    out = result["result"]
    assert out["status"] == 200 and out["data"] is None
    assert out["processing"] == "completed"
    assert "did not arrive in time" in out["warnings"][0]


def test_the_step_limit_covers_reading_the_body_of_a_read() -> None:
    now = [0.0]
    fake = FakeYouTube(SlowBody(now))
    result = run(READ, READ_INPUT, fake, clock=lambda: now[0])
    assert result["error_code"] == "timeout"
    assert result["definitely_no_external_effect"] is True


def test_no_request_starts_without_time_left() -> None:
    ticks = iter([0.0] + [1000.0] * 10)
    fake = FakeYouTube()
    result = run(READ, READ_INPUT, fake, clock=lambda: next(ticks))
    assert result["error_code"] == "timeout" and fake.calls == []


def test_a_too_large_answer_to_a_write_is_kept_and_to_a_read_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from runtime import generic

    monkeypatch.setattr(generic, "MAX_ANSWER_BYTES", 1000)
    big = raw(200, b'{"a":"' + b"x" * 5000 + b'"}')
    result = run(WRITE, WRITE_INPUT, FakeYouTube(big))
    assert result["ok"] is True and result["external_effect_status"] == "succeeded"
    assert result["result"]["data"] is None
    assert "is larger than" in result["result"]["warnings"][0]
    big = raw(200, b'{"a":"' + b"x" * 5000 + b'"}')
    result = run(READ, READ_INPUT, FakeYouTube(big))
    assert result["error_code"] == "response_too_large"
    assert result["definitely_no_external_effect"] is True


def test_decimals_are_sent_exactly_never_through_float() -> None:
    value = Decimal("12345678901234567890.123456789")
    assert dumps_json({"amount": value, "n": [Decimal("0.10")]}) == (
        '{"amount":12345678901234567890.123456789,"n":[0.10]}'
    )


def test_a_socket_error_is_not_a_secret_leak() -> None:
    fake = FakeYouTube(socket.gaierror(f"name {TOKEN}"))
    result = run(READ, READ_INPUT, fake)
    assert TOKEN not in text_of(result)


def test_the_error_form_is_googles_for_the_status() -> None:
    from support import payload

    t = transport.YouTubeTransport(connection_from_payload(payload("x"), connection_ref=""))
    assert t.error_form(b'{"error": {"code": 400, "message": "m"}}', 400)
    assert not t.error_form(b'{"error": {"code": 400, "message": "m"}}', 404)
    assert not t.error_form(b'{"error": {"code": 400}}', 400)
    assert not t.error_form(b'{"error": "unauthorized"}', 401)
    assert not t.error_form(b"{}", 400) and not t.error_form(b"oops", 400)


def test_a_token_written_with_json_escapes_is_still_removed() -> None:
    escaped = "".join(f"\\u{ord(ch):04x}" for ch in TOKEN)
    body = ('{"error": {"code": 400, "message": "' + escaped + '"}}').encode()
    result = run(READ, READ_INPUT, FakeYouTube(refuse(400, body)))
    assert TOKEN not in text_of(result) and "[redacted]" in result["error"]


def test_an_internal_error_logs_its_place_and_never_the_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from runtime import generic

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"boom {TOKEN}")

    monkeypatch.setattr(generic, "read_result", broken)
    result = run(READ, READ_INPUT, FakeYouTube(ok({"items": []})))
    assert result["error_code"] == "internal_error"
    assert result["definitely_no_external_effect"] is True
    captured = capsys.readouterr()
    assert TOKEN not in captured.err + captured.out + text_of(result)
    assert "RuntimeError" in captured.err


def test_an_internal_error_after_a_write_was_sent_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from runtime import generic

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(generic, "write_result", broken)
    result = run(WRITE, WRITE_INPUT, FakeYouTube(ok({"id": "PL1"})))
    assert result["external_effect_status"] == "timeout_unknown"
    assert result["definitely_no_external_effect"] is False


@pytest.mark.parametrize("status", [200, 201, 204])
def test_any_2xx_is_a_success(status: int) -> None:
    body = None if status == 204 else {"id": "PL1"}
    assert run(WRITE, WRITE_INPUT, FakeYouTube(ok(body, status)))["ok"] is True


# -- numbers outside the bounds ------------------------------------------------------------


def test_huge_numbers_in_an_answer_after_a_write_keep_the_structured_result() -> None:
    body = b'{"id":"1","n":12.50,"big":1e1000000,"small":1e-1000000,"m":' + b"9" * 5000 + b"}"
    result = run(WRITE, WRITE_INPUT, FakeYouTube(raw(200, body)))
    assert result["ok"] is True, result
    data = result["result"]["data"]
    assert data["id"] == "1" and data["n"] == "12.50"
    assert data["big"] == "1e1000000" and data["small"] == "1e-1000000"
    assert data["m"] == "9" * 5000
    assert len(text_of(result)) < 20_000


def test_a_huge_number_in_a_read_answer_is_text_not_expanded() -> None:
    fake = FakeYouTube(raw(200, b'{"items":[],"x":-2.5E+99999}'))
    result = run(READ, READ_INPUT, fake)
    assert result["ok"] is True and result["result"]["data"]["x"] == "-2.5E+99999"


@pytest.mark.parametrize(
    ("text", "inside"),
    [
        ("1" * 40, True),
        ("1" * 41, False),
        ("1e30", True),
        ("1e31", False),
        ("1e-30", True),
        ("1e-31", False),
        ("12345.678", True),
    ],
)
def test_the_number_bounds_come_from_digits_and_exponent(text: str, inside: bool) -> None:
    from runtime import numbers

    assert numbers.bounded(Decimal(text)) is inside
    integer = text.isdigit()
    assert (numbers.read(text, integer=integer) is not None) is inside


def test_a_decimal_outside_the_bounds_is_never_expanded_when_written() -> None:
    assert dumps_json({"x": Decimal("1e1000000")}) == '{"x":"1E+1000000"}'
    assert dumps_json({"x": Decimal("49.90")}) == '{"x":49.90}'


def test_an_answer_nested_too_deeply_is_not_read() -> None:
    body = b'{"items":[],"x":' + b"[" * 60 + b"]" * 60 + b"}"
    result = run(READ, READ_INPUT, FakeYouTube(raw(200, body)))
    assert result["error_code"] == "invalid_response"
    assert "nested deeper" in result["error"]
