"""An answer cut off before its end is never taken for a whole one.

A real HTTP server on 127.0.0.1 sends the status, the headers and only part of the body,
then closes the connection: ``Content-Length`` promises more bytes than arrive, or a
chunked answer stops before its last chunk. ``http.client`` returns the short body of
the first case without an error, so the transport compares what arrived with what was
promised. A read is an error that changed nothing; a write YouTube confirmed by its
status follows table T (data null with a warning, or "created, id not known"); a file is
not saved.
"""

from __future__ import annotations

import socket
import threading
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest
from support import Artifacts, run

READ = ("get_channels", {"part": ["snippet"], "mine": True})
WRITE = ("update_playlist", {"part": ["snippet"], "body": {"id": "PL1", "snippet": {"title": "N"}}})


def _cut_by_length(body: bytes = b"{}", promised: int = 10) -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {promised}\r\n\r\n".encode()
        + body
    )


def _cut_chunked() -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        b'Transfer-Encoding: chunked\r\n\r\n5\r\n{"id"\r\n'
    )


class Server:
    """Answers every connection with ``answer`` and closes it."""

    def __init__(self, answer: bytes) -> None:
        self.answer = answer
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.requests = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                data = b""
                while b"\r\n\r\n" not in data:
                    part = conn.recv(65536)
                    if not part:
                        break
                    data += part
                head, _, rest = data.partition(b"\r\n\r\n")
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        missing = int(line.split(b":")[1]) - len(rest)
                        while missing > 0:
                            part = conn.recv(65536)
                            if not part:
                                break
                            missing -= len(part)
                self.requests += 1
                conn.sendall(self.answer)

    def opener(self, request: Any, *, timeout_seconds: float, purpose: str) -> Any:
        """Sends the request to this server instead of YouTube, over plain HTTP."""
        _, _, rest = request.full_url.partition("://")
        path = "/" + rest.partition("/")[2]
        local = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=request.data,
            method=request.get_method(),
            headers=dict(request.header_items()),
        )
        return urllib.request.urlopen(local, timeout=timeout_seconds)

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def serve() -> Iterator[Any]:
    servers: list[Server] = []

    def start(answer: bytes) -> Server:
        server = Server(answer)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


@pytest.mark.parametrize("answer", [_cut_by_length(), _cut_chunked()], ids=["length", "chunked"])
def test_a_read_cut_off_is_an_error_without_effect(serve: Any, answer: bytes) -> None:
    server = serve(answer)
    result = run(*READ, server.opener)
    assert server.requests == 1
    assert result["ok"] is False
    assert result["error_code"] == "invalid_response"
    assert "cut off" in result["error"]
    assert result["definitely_no_external_effect"] is True


def test_a_whole_answer_with_its_length_is_read(serve: Any) -> None:
    body = b'{"items": []}'
    result = run(*READ, serve(_cut_by_length(body, len(body))).opener)
    assert result["ok"] is True


@pytest.mark.parametrize("answer", [_cut_by_length(), _cut_chunked()], ids=["length", "chunked"])
def test_a_confirmed_write_cut_off_succeeds_without_data_and_warns(
    serve: Any, answer: bytes
) -> None:
    result = run(*WRITE, serve(answer).opener)
    assert result["ok"] is True
    out = result["result"]
    assert out["data"] is None and out["applied"] is True
    assert any("was cut off" in warning for warning in out["warnings"])


def test_a_creation_cut_off_says_it_was_created_without_its_id(serve: Any) -> None:
    # The part that arrived is valid JSON with an id; the rest is still missing.
    body = b'{"id": "PL1"}'
    answer = _cut_by_length(body, len(body) + 40)
    result = run("create_playlist", {"title": "Launch"}, serve(answer).opener)
    assert result["ok"] is False
    assert result["error_code"] == "invalid_response"
    assert result["external_effect_status"] == "timeout_unknown"
    assert "was created" in result["error"]


def test_a_file_cut_off_is_not_saved(serve: Any) -> None:
    answer = b"HTTP/1.1 200 OK\r\nContent-Type: text/vtt\r\nContent-Length: 100\r\n\r\nWEBVTT\n"
    artifacts = Artifacts()
    result = run("download_caption_track", {"id": "c1"}, serve(answer).opener, artifacts=artifacts)
    assert result["ok"] is False
    assert result["error_code"] == "invalid_response"
    assert artifacts.saved == []


def test_an_empty_body_where_json_is_documented_is_an_invalid_answer(serve: Any) -> None:
    result = run("get_content_regions", {"part": ["snippet"]}, serve(_cut_by_length(b"", 0)).opener)
    assert result["ok"] is False
    assert result["error_code"] == "invalid_response"
    assert result["definitely_no_external_effect"] is True
