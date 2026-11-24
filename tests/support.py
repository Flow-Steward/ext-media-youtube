"""A fake YouTube API, an in-memory artifact plane and helpers."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Iterator
from decimal import Decimal
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

from runtime.operations import handle_runtime
from runtime.transport import YouTubeTransport, parse_json

BUNDLE = Path(__file__).resolve().parents[1]
TOKEN = "ya29.youtube-fixture-access-token-0123456789abcdef"  # pragma: allowlist secret
JSON = "application/json; charset=UTF-8"


class Call:
    def __init__(self, request: Any) -> None:
        parts = urlsplit(request.full_url)
        self.url = request.full_url
        self.host = parts.hostname
        self.path = parts.path
        self.query = parse_qsl(parts.query, keep_blank_values=True)
        self.verb = request.get_method()
        self.headers = {k.lower(): v for k, v in request.header_items()}
        self.raw_body = request.data or b""
        try:
            self.body: Any = parse_json(self.raw_body) if self.raw_body else None
        except ValueError:
            self.body = None

    @property
    def key(self) -> str:
        return f"{self.verb} {self.path}"


class Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = Message()
        for key, value in (headers or {"Content-Type": JSON}).items():
            self.headers[key] = value

    def read(self, size: int = -1) -> bytes:
        chunk, self._body = (
            (self._body, b"") if size < 0 else (self._body[:size], self._body[size:])
        )
        return chunk

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def ok(value: Any = None, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    raw = b"" if value is None else json.dumps(value, default=str).encode("utf-8")
    return Response(status, raw, headers)


def raw(status: int, body: bytes, content_type: str = JSON, **headers: str) -> Response:
    return Response(status, body, {"Content-Type": content_type, **headers})


def refuse(status: int, body: Any = None, **headers: str) -> HTTPError:
    data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    message = Message()
    message["Content-Type"] = JSON
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return HTTPError(
        "https://youtube.googleapis.com/x", status, "refused", message, io.BytesIO(data)
    )


def google_error(
    status: int = 400, reason: str = "invalidValue", message: str = "Bad value"
) -> dict[str, Any]:
    """Google's error object for HTTP ``status``."""
    return {
        "error": {
            "code": status,
            "message": message,
            "errors": [{"message": message, "domain": "youtube", "reason": reason}],
        }
    }


Handler = Callable[[Call], Any]


class FakeYouTube:
    """Answers requests in order (a list) or by key (``"GET /youtube/v3/channels"`` -> answer)."""

    def __init__(self, *answers: Any, routes: dict[str, Any] | None = None) -> None:
        self.answers = list(answers)
        self.routes = routes or {}
        self.calls: list[Call] = []

    def __call__(self, request: Any, *, timeout_seconds: float, purpose: str) -> Any:
        call = Call(request)
        self.calls.append(call)
        if call.key in self.routes:
            answer = self.routes[call.key]
            if isinstance(answer, list):
                answer = answer.pop(0)
        elif self.answers:
            answer = self.answers.pop(0)
        else:
            raise AssertionError(f"unexpected request {call.key}")
        if callable(answer) and not isinstance(answer, (Response, HTTPError)):
            answer = answer(call)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Artifacts:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = dict(files or {})
        self.saved: list[dict[str, Any]] = []

    def reader(
        self, payload: Any, *, artifact_id: str, chunk_size: int, timeout_seconds: float
    ) -> Iterator[bytes]:
        """Like the SDK's ``stream_artifact_bytes``: the file in chunks of ``chunk_size``."""
        data = self.files[artifact_id]
        for start in range(0, len(data), chunk_size):
            yield data[start : start + chunk_size]

    def writer(self, payload: Any, chunks: list[bytes], **kwargs: Any) -> dict[str, Any]:
        data = b"".join(chunks)
        handle = f"artifact-{len(self.saved) + 1}"
        self.saved.append({"handle": handle, "data": data, **kwargs})
        return {"artifact_handle": handle}


def payload(
    operation_id: str,
    operation_input: dict[str, Any] | None = None,
    *,
    connection_type: str = "youtube_channel",
    token: str = TOKEN,
    test_mode: bool = False,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_connection = connection or {
        "connection_id": "conn-1",
        "connection_type": connection_type,
        "oauth_provider_id": "google_youtube",
        "config": {"oauth": {"lifecycle_status": "connected", "subject": "123"}},
        "secrets": {"access_token": token},
    }
    return {
        "mode": "action",
        "contract_version": "extension_host_v2",
        "runtime_context": {
            "test_mode": test_mode,
            "group_id": None,
            "for_each_id": None,
            "step_id": "step-1",
            "step_execution_id": "exec-1",
        },
        "action": {
            "action_id": operation_id,
            "input": {"connection_ref": "conn-1", **(operation_input or {})},
            "target": {"connection": target_connection},
        },
    }


def run(
    operation_id: str,
    operation_input: dict[str, Any] | None = None,
    fake: FakeYouTube | None = None,
    *,
    artifacts: Artifacts | None = None,
    clock: Callable[[], float] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    fake = fake if fake is not None else FakeYouTube()
    artifacts = artifacts or Artifacts()

    def factory(connection: Any) -> YouTubeTransport:
        if clock is None:
            return YouTubeTransport(connection, opener=fake)
        return YouTubeTransport(connection, opener=fake, clock=clock)

    return handle_runtime(
        payload(operation_id, operation_input, **kwargs),
        transport_factory=factory,
        artifact_reader=artifacts.reader,
        artifact_writer=artifacts.writer,
    )


def text_of(response: dict[str, Any]) -> str:
    return json.dumps(response, default=str)


def dec(value: str) -> Decimal:
    return Decimal(value)
