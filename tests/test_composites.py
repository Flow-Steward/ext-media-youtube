"""The everyday steps."""

from __future__ import annotations

from typing import Any

import pytest
from support import Artifacts, FakeYouTube, google_error, ok, refuse, run

from runtime import budget, composites

CHANNEL = {
    "id": "UC1",
    "snippet": {"title": "My channel", "customUrl": "@mine"},
    "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
}


def channels(*items: dict[str, Any]) -> Any:
    return ok({"items": list(items)})


# -- connection ------------------------------------------------------------------------------


def test_test_connection_returns_the_channel() -> None:
    fake = FakeYouTube(channels(CHANNEL))
    out = run("test_connection", {}, fake)["result"]
    assert out == {
        "connected": True,
        "channel_id": "UC1",
        "title": "My channel",
        "custom_url": "@mine",
        "connection_type": "youtube_channel",
        "warnings": [],
    }
    assert ("mine", "true") in fake.calls[0].query


def test_an_account_without_a_channel_is_not_found() -> None:
    result = run("test_connection", {}, FakeYouTube(channels()))
    assert result["error_code"] == "not_found"
    assert "YouTube channel" in result["error"]


def test_the_post_connect_action_names_the_channel() -> None:
    out = run("verify_identity", {}, FakeYouTube(channels(CHANNEL)))["result"]
    assert out == {"subject": "UC1", "verified_display_name": "My channel", "health": "ok"}


# -- lists ----------------------------------------------------------------------------------


def test_all_channel_videos_come_from_the_uploads_playlist() -> None:
    fake = FakeYouTube(
        channels(CHANNEL),
        ok({"items": [{"id": "i1"}], "nextPageToken": "T2"}),
        ok({"items": [{"id": "i2"}]}),
    )
    out = run("list_channel_videos", {}, fake)["result"]
    assert out["uploads_playlist_id"] == "UU1" and out["channel_id"] == "UC1"
    assert [v["id"] for v in out["videos"]] == ["i1", "i2"]
    assert out["complete"] is True and out["next_page_token"] is None
    assert ("playlistId", "UU1") in fake.calls[1].query
    assert ("maxResults", "50") in fake.calls[1].query


def test_channel_videos_of_another_channel_and_from_a_token() -> None:
    fake = FakeYouTube(channels(CHANNEL), ok({"items": [{"id": "i9"}]}))
    run("list_channel_videos", {"channel_id": "UC1", "page_token": "T9"}, fake)
    assert ("id", "UC1") in fake.calls[0].query
    assert ("pageToken", "T9") in fake.calls[1].query


def test_channel_videos_stop_at_max_videos_with_where_to_continue() -> None:
    fake = FakeYouTube(
        channels(CHANNEL), ok({"items": [{"id": "a"}, {"id": "b"}], "nextPageToken": "T2"})
    )
    out = run("list_channel_videos", {"max_videos": 2}, fake)["result"]
    assert out["count"] == 2 and out["complete"] is False and out["next_page_token"] == "T2"
    assert ("maxResults", "2") in fake.calls[1].query


def test_channel_videos_can_go_to_a_file() -> None:
    artifacts = Artifacts()
    fake = FakeYouTube(channels(CHANNEL), ok({"items": [{"id": "a"}]}))
    out = run("list_channel_videos", {"output": "file"}, fake, artifacts=artifacts)["result"]
    assert out["videos"] == [] and out["file"] == "artifact-1"
    assert artifacts.saved[0]["data"] == b'[{"id":"a"}]'


def test_a_channel_without_an_uploads_playlist_is_an_invalid_answer() -> None:
    fake = FakeYouTube(channels({"id": "UC1", "contentDetails": {}}))
    result = run("list_channel_videos", {}, fake)
    assert result["error_code"] == "invalid_response"


def test_my_channels_reads_statistics() -> None:
    fake = FakeYouTube(channels({**CHANNEL, "statistics": {"viewCount": "10"}}))
    out = run("list_my_channels", {}, fake)["result"]
    assert out["channels"][0]["statistics"] == {"viewCount": "10"}
    query = fake.calls[0].query
    assert ("part", "statistics") in query and ("mine", "true") in query


def test_all_video_comments_with_replies() -> None:
    fake = FakeYouTube(
        ok({"items": [{"id": "c1"}], "nextPageToken": "T2"}), ok({"items": [{"id": "c2"}]})
    )
    out = run(
        "list_video_comments",
        {"video_id": "V1", "include_replies": True, "order": "time", "text_format": "plainText"},
        fake,
    )["result"]
    assert [c["id"] for c in out["comments"]] == ["c1", "c2"]
    query = fake.calls[0].query
    assert ("part", "replies") in query and ("videoId", "V1") in query
    assert ("order", "time") in query and ("textFormat", "plainText") in query
    assert ("maxResults", "100") in query


def test_comments_disabled_is_a_refusal_not_an_empty_list() -> None:
    fake = FakeYouTube(refuse(403, google_error(403, "commentsDisabled", "disabled")))
    result = run("list_video_comments", {"video_id": "V1"}, fake)
    assert result["ok"] is False and "commentsDisabled" in result["error"]


def test_all_my_playlists() -> None:
    fake = FakeYouTube(ok({"items": [{"id": "PL1"}]}))
    out = run("list_my_playlists", {}, fake)["result"]
    assert out["playlists"] == [{"id": "PL1"}] and out["complete"] is True


# -- videos by id ---------------------------------------------------------------------------


def test_videos_are_read_50_ids_per_request() -> None:
    ids = [f"v{i}" for i in range(120)]
    answers = [
        ok({"items": [{"id": i} for i in ids[n : n + 50] if i != "v7"]}) for n in range(0, 120, 50)
    ]
    fake = FakeYouTube(*answers)
    out = run("get_videos_by_id", {"video_ids": ids}, fake)["result"]
    assert len(fake.calls) == 3
    assert [len([q for q in c.query if q[0] == "id"]) for c in fake.calls] == [50, 50, 20]
    assert out["count"] == 119 and out["missing_ids"] == ["v7"] and out["unread_ids"] == []
    assert ("part", "statistics") in fake.calls[0].query


def test_ids_not_read_after_a_failure_are_unread() -> None:
    ids = [f"v{i}" for i in range(60)]
    fake = FakeYouTube(ok({"items": [{"id": i} for i in ids[:50]]}), refuse(503, b""))
    out = run("get_videos_by_id", {"video_ids": ids}, fake)["result"]
    assert out["count"] == 50 and out["unread_ids"] == ids[50:]
    assert out["missing_ids"] == []
    assert "unread_ids" in out["warnings"][0]


def test_ids_not_read_because_the_output_is_full_are_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(budget, "MAX_SERIALIZED_BYTES", 6000)
    ids = [f"v{i}" for i in range(60)]
    fake = FakeYouTube(
        ok({"items": [{"id": "v0", "t": "x" * 2000}]}),
        ok({"items": [{"id": "v50", "t": "x" * 3000}]}),
    )
    out = run("get_videos_by_id", {"video_ids": ids}, fake)["result"]
    assert out["unread_ids"] == ids[50:]
    assert budget.fits(out)


@pytest.mark.parametrize("ids", [[], ["bad id"], "v1"])
def test_video_ids_are_checked(ids: Any) -> None:
    result = run("get_videos_by_id", {"video_ids": ids}, FakeYouTube())
    assert result["error_code"] == "invalid_payload"


# -- processing status ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "details", "finished"),
    [
        ({"uploadStatus": "uploaded"}, {"processingStatus": "processing"}, False),
        ({"uploadStatus": "processed"}, {"processingStatus": "succeeded"}, True),
        ({"uploadStatus": "failed", "failureReason": "codec"}, {}, True),
        ({"uploadStatus": "rejected", "rejectionReason": "duplicate"}, {}, True),
        ({"uploadStatus": "uploaded"}, {"processingStatus": "terminated"}, True),
    ],
)
def test_the_processing_status(
    status: dict[str, Any], details: dict[str, Any], finished: bool
) -> None:
    video = {"id": "V1", "status": status}
    if details:
        video["processingDetails"] = details
    out = run(
        "get_video_processing_status", {"video_id": "V1"}, FakeYouTube(ok({"items": [video]}))
    )["result"]
    assert out["finished"] is finished
    assert out["upload_status"] == status["uploadStatus"]
    if status.get("failureReason"):
        assert out["failure_reason"] == "codec"
    if status.get("rejectionReason"):
        assert out["rejection_reason"] == "duplicate"
    if not details:
        assert "only to the video's owner" in out["warnings"][0]


def test_a_video_that_is_gone_is_not_found() -> None:
    result = run("get_video_processing_status", {"video_id": "V1"}, FakeYouTube(ok({"items": []})))
    assert result["error_code"] == "not_found"


# -- writes ---------------------------------------------------------------------------------


def test_update_video_details_keeps_what_is_not_given() -> None:
    current = {
        "id": "V1",
        "snippet": {
            "title": "Old",
            "description": "desc",
            "tags": ["a"],
            "categoryId": "22",
            "channelTitle": "not mutable",
        },
    }
    fake = FakeYouTube(ok({"items": [current]}), ok({"id": "V1", "snippet": {"title": "New"}}))
    result = run("update_video_details", {"video_id": "V1", "title": "New"}, fake)
    assert result["ok"] is True, result
    read, write = fake.calls
    assert ("part", "snippet") in read.query and ("id", "V1") in read.query
    assert write.verb == "PUT" and ("part", "snippet") in write.query
    assert write.body == {
        "id": "V1",
        "snippet": {"title": "New", "description": "desc", "tags": ["a"], "categoryId": "22"},
    }
    assert result["result"]["updated_parts"] == ["snippet"]


def test_update_video_details_sends_status_with_its_current_fields() -> None:
    current = {
        "id": "V1",
        "status": {"privacyStatus": "public", "embeddable": True, "uploadStatus": "processed"},
    }
    fake = FakeYouTube(ok({"items": [current]}), ok({"id": "V1"}))
    run("update_video_details", {"video_id": "V1", "made_for_kids": False}, fake)
    assert fake.calls[1].body == {
        "id": "V1",
        "status": {"privacyStatus": "public", "embeddable": True, "selfDeclaredMadeForKids": False},
    }


def test_publish_at_needs_private() -> None:
    result = run(
        "update_video_details",
        {"video_id": "V1", "privacy_status": "public", "publish_at": "2026-12-01T09:00:00Z"},
        FakeYouTube(),
    )
    assert result["error_code"] == "invalid_payload"
    current = {"id": "V1", "status": {"privacyStatus": "public"}}
    fake = FakeYouTube(ok({"items": [current]}))
    result = run(
        "update_video_details", {"video_id": "V1", "publish_at": "2026-12-01T09:00:00Z"}, fake
    )
    assert result["error_code"] == "invalid_payload" and len(fake.calls) == 1


def test_update_video_details_needs_a_change() -> None:
    result = run("update_video_details", {"video_id": "V1"}, FakeYouTube())
    assert result["error_code"] == "invalid_payload"


def test_reply_to_comment_returns_the_new_id() -> None:
    fake = FakeYouTube(ok({"id": "R1", "snippet": {"parentId": "C1"}}))
    out = run("reply_to_comment", {"parent_id": "C1", "text": "Thanks!"}, fake)["result"]
    assert out["comment_id"] == "R1" and out["processing"] == "completed"
    assert fake.calls[0].body == {"snippet": {"parentId": "C1", "textOriginal": "Thanks!"}}
    assert fake.calls[0].path == "/youtube/v3/comments"


def test_create_playlist_is_private_by_default() -> None:
    fake = FakeYouTube(ok({"id": "PL9"}))
    out = run("create_playlist", {"title": "Launch", "description": "d"}, fake)["result"]
    assert out["playlist_id"] == "PL9"
    assert fake.calls[0].body == {
        "snippet": {"title": "Launch", "description": "d"},
        "status": {"privacyStatus": "private"},
    }


def test_add_video_to_playlist_at_a_position() -> None:
    fake = FakeYouTube(ok({"id": "PLI1"}))
    out = run(
        "add_video_to_playlist", {"playlist_id": "PL1", "video_id": "V1", "position": 0}, fake
    )
    assert out["result"]["playlist_item_id"] == "PLI1"
    assert fake.calls[0].body == {
        "snippet": {
            "playlistId": "PL1",
            "resourceId": {"kind": "youtube#video", "videoId": "V1"},
            "position": 0,
        }
    }


@pytest.mark.parametrize("operation_id", sorted(composites.COMPOSITE_WRITES))
def test_a_test_run_of_an_everyday_write_sends_nothing(operation_id: str) -> None:
    given = {
        "upload_video": {"file": "f", "title": "t"},
        "update_video_details": {"video_id": "V1", "title": "t"},
        "set_video_thumbnail": {"video_id": "V1", "file": "f"},
        "reply_to_comment": {"parent_id": "C1", "text": "x"},
        "create_playlist": {"title": "t"},
        "add_video_to_playlist": {"playlist_id": "PL1", "video_id": "V1"},
    }[operation_id]
    fake = FakeYouTube()
    result = run(operation_id, given, fake, test_mode=True)
    assert result["ok"] is True, result
    assert fake.calls == []
    assert result["definitely_no_external_effect"] is True
    assert result["result"]["processing"] is None and result["result"]["applied"] is False
