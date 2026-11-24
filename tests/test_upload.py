"""YouTube's resumable upload of a workflow file (runtime/upload.py)."""

from __future__ import annotations

import tracemalloc
from typing import Any

import pytest
from support import TOKEN, Artifacts, FakeYouTube, google_error, ok, refuse, run, text_of

from runtime import upload

SESSION = (
    "https://youtube.googleapis.com/upload/youtube/v3/videos?uploadType=resumable"
    "&upload_id=ADPycdSecretUploadId0123456789"
)
UPLOAD_ID = "ADPycdSecretUploadId0123456789"
MIB = 1024 * 1024


def opened(location: str = SESSION) -> Any:
    return ok(None, 200, {"Location": location})


def video(size: int) -> Artifacts:
    return Artifacts({"vid": b"v" * size})


def upload_input(**extra: Any) -> dict[str, Any]:
    return {"file": "vid", "title": "Clip", "content_type": "video/mp4", **extra}


def test_a_small_file_is_one_session_and_one_part() -> None:
    fake = FakeYouTube(opened(), ok({"id": "VID1", "status": {"uploadStatus": "uploaded"}}))
    result = run(
        "upload_video", upload_input(description="d", tags=["a"]), fake, artifacts=video(10)
    )
    assert result["ok"] is True, result
    start, part = fake.calls
    assert start.verb == "POST" and start.path == "/upload/youtube/v3/videos"
    assert ("uploadType", "resumable") in start.query
    assert ("part", "snippet") in start.query and ("part", "status") in start.query
    assert start.headers["x-upload-content-type"] == "video/mp4"
    assert start.headers["x-upload-content-length"] == "10"
    assert start.body == {
        "snippet": {"title": "Clip", "description": "d", "tags": ["a"]},
        "status": {"privacyStatus": "private"},
    }
    assert part.verb == "PUT" and part.url == SESSION
    assert part.headers["content-range"] == "bytes 0-9/10"
    assert part.headers["content-type"] == "video/mp4"
    assert part.raw_body == b"v" * 10
    out = result["result"]
    assert out["video_id"] == "VID1" and out["upload_status"] == "uploaded"
    assert out["processing"] == "accepted" and out["applied"] is False
    assert out["check"] == {"operation_id": "get_video_processing_status"}


def test_a_large_file_goes_in_parts_of_8_mib() -> None:
    size = 2 * upload.CHUNK_BYTES + 5
    fake = FakeYouTube(
        opened(),
        refuse(308, b"", Range=f"bytes=0-{upload.CHUNK_BYTES - 1}"),
        refuse(308, b"", Range=f"bytes=0-{2 * upload.CHUNK_BYTES - 1}"),
        ok({"id": "VID1"}),
    )
    result = run("upload_video", upload_input(), fake, artifacts=video(size))
    assert result["ok"] is True, result
    ranges = [c.headers.get("content-range") for c in fake.calls[1:]]
    assert ranges == [
        f"bytes 0-{upload.CHUNK_BYTES - 1}/{size}",
        f"bytes {upload.CHUNK_BYTES}-{2 * upload.CHUNK_BYTES - 1}/{size}",
        f"bytes {2 * upload.CHUNK_BYTES}-{size - 1}/{size}",
    ]
    assert upload.CHUNK_BYTES % (256 * 1024) == 0


def test_bytes_youtube_did_not_keep_are_sent_again() -> None:
    size = upload.CHUNK_BYTES + 10
    fake = FakeYouTube(opened(), refuse(308, b"", Range="bytes=0-99"), ok({"id": "VID1"}))
    result = run("upload_video", upload_input(), fake, artifacts=video(size))
    assert result["ok"] is True, result
    assert fake.calls[2].headers["content-range"] == f"bytes 100-{size - 1}/{size}"
    assert fake.calls[2].raw_body == b"v" * (size - 100)


def test_the_session_address_never_reaches_a_result_or_an_error() -> None:
    fake = FakeYouTube(
        opened(), refuse(400, google_error(400, "invalidValue", f"bad {SESSION} {UPLOAD_ID}"))
    )
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["ok"] is False
    assert UPLOAD_ID not in text_of(result) and "uploadType" not in text_of(result)
    assert TOKEN not in text_of(result)


def test_a_refused_part_before_the_last_created_nothing() -> None:
    size = upload.CHUNK_BYTES + 10
    fake = FakeYouTube(opened(), refuse(503, b""))
    result = run("upload_video", upload_input(), fake, artifacts=video(size))
    assert result["ok"] is False
    assert result["definitely_no_external_effect"] is True
    assert result["external_effect_status"] == "failed"
    assert "nothing was created" in result["error"]
    assert len(fake.calls) == 2


def test_a_lost_answer_to_the_last_part_is_unknown() -> None:
    fake = FakeYouTube(opened(), TimeoutError())
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["external_effect_status"] == "timeout_unknown"
    assert result["definitely_no_external_effect"] is False


def test_a_last_part_refused_in_googles_form_created_nothing() -> None:
    fake = FakeYouTube(opened(), refuse(400, google_error(400, "invalidTitle")))
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["definitely_no_external_effect"] is True
    assert "invalidTitle" in result["error"]


def test_a_session_refused_created_nothing() -> None:
    fake = FakeYouTube(refuse(403, google_error(403, "quotaExceeded")))
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["error_code"] == "rate_limited"
    assert result["definitely_no_external_effect"] is True
    assert len(fake.calls) == 1


def test_a_session_without_an_address_created_nothing() -> None:
    fake = FakeYouTube(ok(None, 200, {}))
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["error_code"] == "invalid_response"
    assert result["definitely_no_external_effect"] is True


def test_a_session_on_another_host_is_not_used() -> None:
    fake = FakeYouTube(opened("https://evil.example/upload?upload_id=x"))
    result = run("upload_video", upload_input(), fake, artifacts=video(10))
    assert result["error_code"] == "invalid_response"
    assert result["definitely_no_external_effect"] is True
    assert len(fake.calls) == 1


def test_a_part_that_makes_no_progress_stops_the_upload() -> None:
    size = upload.CHUNK_BYTES + 10
    fake = FakeYouTube(opened(), *[refuse(308, b"") for _ in range(upload.MAX_STALLS)])
    result = run("upload_video", upload_input(), fake, artifacts=video(size))
    assert result["error_code"] == "invalid_response"
    assert result["definitely_no_external_effect"] is True
    assert len(fake.calls) == 1 + upload.MAX_STALLS


def test_a_range_that_is_not_bytes_is_refused() -> None:
    size = upload.CHUNK_BYTES + 10
    fake = FakeYouTube(opened(), refuse(308, b"", Range="items=0-3"))
    result = run("upload_video", upload_input(), fake, artifacts=video(size))
    assert result["error_code"] == "invalid_response"


def test_time_running_out_before_the_last_part_created_nothing() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    size = upload.CHUNK_BYTES + 10

    def slow(call: Any) -> Any:
        now[0] += 560
        return refuse(308, b"", Range=f"bytes=0-{upload.CHUNK_BYTES - 1}")

    fake = FakeYouTube(opened(), slow)
    result = run("upload_video", upload_input(), fake, artifacts=video(size), clock=clock)
    assert result["ok"] is False
    assert result["definitely_no_external_effect"] is True
    assert "nothing was created" in result["error"]


def test_a_file_larger_than_the_host_allows_is_refused_before_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FS_EXTENSION_ARTIFACT_MAX_BYTES", "100")
    fake = FakeYouTube()
    result = run("upload_video", upload_input(), fake, artifacts=video(101))
    assert result["error_code"] == "invalid_payload"
    assert "larger than" in result["error"]
    assert fake.calls == []


def test_a_media_type_the_method_does_not_accept_is_refused() -> None:
    result = run(
        "upload_video", upload_input(content_type="image/png"), FakeYouTube(), artifacts=video(10)
    )
    assert result["error_code"] == "invalid_payload"
    assert "video/*" in result["error"]


def test_a_generated_upload_sends_metadata_and_file() -> None:
    artifacts = Artifacts({"cap": b"1\n00:00:01,000 --> 00:00:02,000\nhi\n"})
    session = SESSION.replace("videos", "captions")
    fake = FakeYouTube(opened(session), ok({"id": "CAP1"}))
    given = {
        "part": ["snippet"],
        "body": {"snippet": {"videoId": "V1", "language": "en", "name": "English"}},
        "file": "cap",
    }
    result = run("upload_caption_track", given, fake, artifacts=artifacts)
    assert result["ok"] is True, result
    start, part = fake.calls
    assert start.path == "/upload/youtube/v3/captions"
    assert start.body == given["body"]
    assert part.headers["content-type"] == "application/octet-stream"
    assert result["result"]["data"] == {"id": "CAP1"}


def test_an_update_without_a_file_is_an_ordinary_write() -> None:
    fake = FakeYouTube(ok({"id": "CAP1"}))
    given = {"part": ["snippet"], "body": {"id": "CAP1", "snippet": {"isDraft": False}}}
    result = run("update_caption_track", given, fake)
    assert result["ok"] is True
    assert fake.calls[0].path == "/youtube/v3/captions" and fake.calls[0].verb == "PUT"


def test_an_insert_needs_its_file() -> None:
    result = run("upload_channel_banner", {}, FakeYouTube())
    assert result["error_code"] == "invalid_payload" and "file is required" in result["error"]


def test_content_type_without_file_is_refused() -> None:
    given = {"part": ["snippet"], "body": {"id": "CAP1"}, "content_type": "text/xml"}
    result = run("update_caption_track", given, FakeYouTube())
    assert result["error_code"] == "invalid_payload"


def test_a_thumbnail_is_uploaded_for_its_video() -> None:
    artifacts = Artifacts({"img": b"\x89PNG"})
    session = SESSION.replace("videos", "thumbnails/set")
    fake = FakeYouTube(opened(session), ok({"items": [{"default": {"url": "u"}}]}))
    result = run(
        "set_video_thumbnail",
        {"video_id": "V1", "file": "img", "content_type": "image/png"},
        fake,
        artifacts=artifacts,
    )
    assert result["ok"] is True, result
    start = fake.calls[0]
    assert start.path == "/upload/youtube/v3/thumbnails/set"
    assert ("videoId", "V1") in start.query
    assert result["result"]["processing"] == "completed"


#: Parts of the memory test's file.
MEMORY_TEST_PARTS = 5


def _counting_youtube(size: int) -> tuple[Any, list[int]]:
    """Answers an upload like YouTube and keeps only the size of each request body, so
    the test measures the extension's memory, not the fake's."""
    sizes: list[int] = []

    def opener(request: Any, *, timeout_seconds: float, purpose: str) -> Any:
        sizes.append(len(request.data or b""))
        if request.get_method() == "POST":
            return opened()
        sent = sum(sizes[1:])
        if sent < size:
            raise refuse(308, b"", Range=f"bytes=0-{sent - 1}")
        return ok({"id": "VID1"})

    return opener, sizes


def test_an_upload_holds_about_one_part_in_memory() -> None:
    """The file is streamed from storage to a temporary file and sent part by part: the
    peak is about one part, not the file (the file here is five parts)."""
    size = MEMORY_TEST_PARTS * upload.CHUNK_BYTES + 7
    artifacts = video(size)
    opener, sizes = _counting_youtube(size)
    tracemalloc.start()
    try:
        result = run("upload_video", upload_input(), opener, artifacts=artifacts)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result["ok"] is True, result
    assert sum(sizes[1:]) == size
    assert peak < 2 * upload.CHUNK_BYTES, peak


def test_a_file_larger_than_the_cap_stops_while_it_is_read(monkeypatch: Any) -> None:
    monkeypatch.setenv("FS_EXTENSION_ARTIFACT_MAX_BYTES", str(3 * MIB))
    fake = FakeYouTube()
    result = run("upload_video", upload_input(), fake, artifacts=video(4 * MIB))
    assert result["error_code"] == "invalid_payload"
    assert "larger than the 3 MiB" in result["error"]
    assert fake.calls == []
