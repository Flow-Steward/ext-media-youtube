"""The everyday steps, built on the generated steps of runtime/registry.json.

Each one goes through the same checks and transport as the generated step of the method
it calls (generic.prepare / generic.to_call), so documented parameters, refusals and
the token handling are the same. Lists read every page (runtime/pages.py). Writes go
through the one outcome table (runtime/outcome.py); the steps that create something
(Upload video, Create playlist, Add video to playlist, Reply to comment) are of the
class that needs the new id from YouTube's answer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from . import budget, errors, files, generic, outcome, pages, upload
from .context import Context
from .errors import ExtensionError, invalid
from .params import date_time, integer, text
from .transport import Answer, dumps_json

PRIVACY = ["private", "unlisted", "public"]
COMMENT_ORDERS = ["time", "relevance"]
TEXT_FORMATS = ["html", "plainText"]
VIDEO_PARTS = [
    "contentDetails",
    "fileDetails",
    "id",
    "liveStreamingDetails",
    "localizations",
    "paidProductPlacementDetails",
    "player",
    "processingDetails",
    "recordingDetails",
    "snippet",
    "statistics",
    "status",
    "suggestions",
    "topicDetails",
]
DEFAULT_VIDEO_PARTS = ["snippet", "contentDetails", "statistics", "status"]
#: videos.list takes at most 50 IDs per request (the batchGetStats parameter documents
#: the same maximum; videos.list's own maxResults is 50).
IDS_PER_REQUEST = 50
MAX_VIDEO_IDS = 5000
#: Bounds of this extension's own inputs (safety bounds, not YouTube's rules).
MAX_TITLE = 1000
MAX_DESCRIPTION = 20000
MAX_TAGS = 500
MAX_TAG = 500
MAX_TEXT = 20000
#: A YouTube ID as this extension accepts it (video IDs have 11 characters, channel IDs
#: 24, playlist IDs 34; the bound leaves room without accepting arbitrary text).
MAX_ID_LENGTH = 100
#: An RFC 3339 date and time with a fraction and an offset fits in 40 characters.
MAX_DATE_TIME_LENGTH = 40
#: A video category ID (a small number as text).
MAX_CATEGORY_ID_LENGTH = 20
#: A BCP-47 language tag: RFC 5646 section 4.4.1 asks implementations to accept at least
#: 35 characters.
MAX_LANGUAGE_LENGTH = 35
#: A comment ID, which YouTube gives longer than a video ID.
MAX_COMMENT_ID_LENGTH = 200
#: Search terms of a comment list (a safety bound).
MAX_SEARCH_TERMS_LENGTH = 500
#: Channels a user's "my channels" list can hold (a safety bound; a Google account has
#: far fewer).
MAX_MY_CHANNELS = 1000
#: Records the "all" steps read by default and at most (safety bounds that keep a step
#: within its time and output).
DEFAULT_MAX_VIDEOS = 5000
DEFAULT_MAX_PLAYLISTS = 5000
LARGEST_MAX_VIDEOS = 50_000
LARGEST_MAX_PLAYLISTS = 50_000
DEFAULT_MAX_COMMENTS = 10_000
LARGEST_MAX_COMMENTS = 100_000
_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

PROCESSING_STEP = "get_video_processing_status"


# -- helpers -----------------------------------------------------------------------------


def _obj(value: Any) -> Mapping[str, Any]:
    """``value`` when it is a JSON object, else an empty one."""
    return value if isinstance(value, Mapping) else {}


def _closed(given: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    rest = {k: v for k, v in given.items() if k != "connection_ref"}
    unknown = sorted(set(rest) - allowed)
    if unknown:
        raise invalid(
            f"The step input has unknown fields: {', '.join(unknown[: errors.LISTED_NAMES])}"
        )
    return rest


def _read(context: Context, operation_id: str, given: Mapping[str, Any]) -> Any:
    """One read through a generated step; its JSON value."""
    entry = generic.spec(operation_id)
    plan = generic.prepare(operation_id, given)
    answer = context.transport.read(generic.to_call(entry, plan))
    return generic._read_json(context, answer, plan.shown)


def _ident(value: Any, name: str) -> str:
    """A YouTube id: letters, digits, - and _ (at most MAX_ID_LENGTH)."""
    result = text(value, name, max_length=MAX_ID_LENGTH)
    if any(ch not in _ID_CHARS for ch in result):
        raise invalid(f"{name} must be a YouTube ID (letters, digits, - and _)")
    return result


def _opt_int(given: Mapping[str, Any], name: str, *, default: int, low: int, high: int) -> int:
    value = given.get(name)
    if value is None or value == "":
        return default
    return integer({"minimum": low, "maximum": high}, value, name)


def _opt_text(given: Mapping[str, Any], name: str, *, max_length: int) -> str | None:
    value = given.get(name)
    if value is None or value == "":
        return None
    return text(value, name, max_length=max_length)


def _choice(given: Mapping[str, Any], name: str, allowed: list[str], default: str | None) -> Any:
    value = given.get(name)
    if value is None or value == "":
        return default
    if value not in allowed:
        raise invalid(f"{name} must be one of: {', '.join(allowed)}")
    return value


def _flag(given: Mapping[str, Any], name: str) -> bool | None:
    value = given.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise invalid(f"{name} must be true or false")
    return value


def _list(given: Mapping[str, Any], name: str, *, max_items: int, max_length: int) -> list[str]:
    value = given.get(name)
    if value is None or value == [] or value == "":
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise invalid(f"{name} must be a list of at most {max_items} values")
    return [text(v, f"{name} item {i}", max_length=max_length) for i, v in enumerate(value, 1)]


def _output_choice(given: Mapping[str, Any]) -> bool:
    value = given.get("output")
    if value in (None, "", "step"):
        return False
    if value == "file":
        return True
    raise invalid("output must be step or file")


def _publish_at(given: Mapping[str, Any], privacy: str | None) -> str | None:
    value = _opt_text(given, "publish_at", max_length=MAX_DATE_TIME_LENGTH)
    if value is None:
        return None
    if "T" not in value or not (value.endswith("Z") or value[-6] in "+-"):
        raise invalid(
            "publish_at must be a date and time with its zone, such as 2026-12-01T09:00:00Z"
        )
    date_time(value, "publish_at")
    if privacy is not None and privacy != "private":
        # VideoStatus.publishAt: "It can be set only if the privacy status of the video
        # is private."
        raise invalid("publish_at can be set only with privacy_status private")
    return value


def _channel_query(given: Mapping[str, Any]) -> dict[str, Any]:
    channel = given.get("channel_id")
    if channel in (None, ""):
        return {"mine": True}
    return {"id": [_ident(channel, "channel_id")]}


def _first_item(data: Any, shown: str, what: str) -> Mapping[str, Any]:
    items, _, _ = pages.split(data, shown)
    if not items:
        raise errors.no_effect(errors.NOT_FOUND, f"YouTube found no {what}")
    item = items[0]
    if not isinstance(item, Mapping):
        raise pages.bad(shown, "lists an item that is not an object")
    return item


def _id_list(given: Mapping[str, Any], name: str, *, most: int) -> list[str]:
    value = given.get(name)
    if not isinstance(value, list) or not value:
        raise invalid(f"{name} must be a list of 1 to {most} IDs")
    if len(value) > most:
        raise invalid(f"{name} must be a list of 1 to {most} IDs")
    out: list[str] = []
    for item in value:
        ident = _ident(item, f"{name} item")
        if ident not in out:
            out.append(ident)
    return out


# -- test connection and identity --------------------------------------------------------


def _my_channel(context: Context) -> Mapping[str, Any]:
    data = _read(context, "get_channels", {"part": ["id", "snippet"], "mine": True})
    item = _first_item(data, "GET /youtube/v3/channels", "YouTube channel for this Google account")
    if not isinstance(item.get("id"), str) or not item["id"].strip():
        raise pages.bad("GET /youtube/v3/channels", "carries no channel id")
    return item


def test_connection(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, set())
    channel = _my_channel(context)
    snippet = _obj(channel.get("snippet"))
    title = snippet.get("title")
    handle = snippet.get("customUrl")
    return {
        "connected": True,
        "channel_id": errors.safe_text(channel["id"], errors.ID_TEXT),
        "title": errors.safe_text(title, errors.NAME_TEXT) if isinstance(title, str) else None,
        "custom_url": errors.safe_text(handle, errors.NAME_TEXT)
        if isinstance(handle, str)
        else None,
        "connection_type": context.connection.connection_type,
        "warnings": [],
    }


def verify_identity(context: Context) -> dict[str, Any]:
    """The post-connect action: which YouTube channel the authorization is for."""
    channel = _my_channel(context)
    snippet = _obj(channel.get("snippet"))
    title = snippet.get("title")
    return {
        "subject": errors.safe_text(channel["id"], errors.ID_TEXT),
        "verified_display_name": errors.safe_text(title, errors.NAME_TEXT)
        if isinstance(title, str)
        else None,
        "health": "ok",
    }


# -- lists -------------------------------------------------------------------------------


def _list_all(
    context: Context,
    operation_id: str,
    query: dict[str, Any],
    *,
    start: str | None,
    most: int,
    to_file: bool,
    out_key: str,
    extra: dict[str, Any] | None = None,
    skip: int = 0,
) -> dict[str, Any]:
    entry = generic.spec(operation_id)
    pager = entry["pager"]

    def fetch(token: str | None, limit: int) -> Any:
        given = dict(query)
        given[pager["size_input"]] = limit
        if token is not None:
            given[pager["token_input"]] = token
        return _read(context, operation_id, given)

    return pages.collect(
        context,
        fetch=fetch,
        shown=f"{entry['method']} {entry['path']}",
        start=start,
        page_size=pager["max"],
        smallest=pager["min"],
        most=most,
        to_file=to_file,
        out_key=out_key,
        extra=extra,
        skip=skip,
    )


def list_my_channels(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, set())
    _ = given
    return _list_all(
        context,
        "get_channels",
        {"part": ["snippet", "statistics", "contentDetails", "status"], "mine": True},
        start=None,
        most=MAX_MY_CHANNELS,
        to_file=False,
        out_key="channels",
    )


def list_channel_videos(context: Context) -> dict[str, Any]:
    given = _closed(
        context.operation_input, {"channel_id", "max_videos", "page_token", "skip", "output"}
    )
    query = _channel_query(given)
    data = _read(context, "get_channels", {"part": ["contentDetails"], **query})
    channel = _first_item(data, "GET /youtube/v3/channels", "channel")
    details = channel.get("contentDetails")
    related = details.get("relatedPlaylists") if isinstance(details, Mapping) else None
    uploads = related.get("uploads") if isinstance(related, Mapping) else None
    if not isinstance(uploads, str) or not uploads.strip():
        raise pages.bad("GET /youtube/v3/channels", "names no uploads playlist for the channel")
    return _list_all(
        context,
        "get_playlist_items",
        {"part": ["snippet", "contentDetails", "status"], "playlist_id": uploads},
        start=_opt_text(given, "page_token", max_length=pages.MAX_TOKEN),
        skip=_opt_int(given, "skip", default=0, low=0, high=generic.MAX_ITEMS),
        most=_opt_int(
            given, "max_videos", default=DEFAULT_MAX_VIDEOS, low=1, high=LARGEST_MAX_VIDEOS
        ),
        to_file=_output_choice(given),
        out_key="videos",
        extra={
            "channel_id": channel.get("id") if isinstance(channel.get("id"), str) else None,
            "uploads_playlist_id": uploads,
        },
    )


def list_video_comments(context: Context) -> dict[str, Any]:
    given = _closed(
        context.operation_input,
        {
            "video_id",
            "order",
            "search_terms",
            "text_format",
            "include_replies",
            "max_comments",
            "page_token",
            "skip",
            "output",
        },
    )
    query: dict[str, Any] = {
        "part": ["snippet", "replies"] if _flag(given, "include_replies") else ["snippet"],
        "video_id": _ident(given.get("video_id"), "video_id"),
    }
    order = _choice(given, "order", COMMENT_ORDERS, None)
    if order:
        query["order"] = order
    fmt = _choice(given, "text_format", TEXT_FORMATS, None)
    if fmt:
        query["text_format"] = fmt
    terms = _opt_text(given, "search_terms", max_length=MAX_SEARCH_TERMS_LENGTH)
    if terms:
        query["search_terms"] = terms
    return _list_all(
        context,
        "get_comment_threads",
        query,
        start=_opt_text(given, "page_token", max_length=pages.MAX_TOKEN),
        skip=_opt_int(given, "skip", default=0, low=0, high=generic.MAX_ITEMS),
        most=_opt_int(
            given, "max_comments", default=DEFAULT_MAX_COMMENTS, low=1, high=LARGEST_MAX_COMMENTS
        ),
        to_file=_output_choice(given),
        out_key="comments",
    )


def list_my_playlists(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"max_playlists", "page_token", "skip"})
    return _list_all(
        context,
        "get_playlists",
        {"part": ["snippet", "contentDetails", "status"], "mine": True},
        start=_opt_text(given, "page_token", max_length=pages.MAX_TOKEN),
        skip=_opt_int(given, "skip", default=0, low=0, high=generic.MAX_ITEMS),
        most=_opt_int(
            given,
            "max_playlists",
            default=DEFAULT_MAX_PLAYLISTS,
            low=1,
            high=LARGEST_MAX_PLAYLISTS,
        ),
        to_file=False,
        out_key="playlists",
    )


# -- videos by id ------------------------------------------------------------------------


def _parts(given: Mapping[str, Any]) -> list[str]:
    value = given.get("parts")
    if value in (None, [], ""):
        return list(DEFAULT_VIDEO_PARTS)
    if not isinstance(value, list) or not value or any(v not in VIDEO_PARTS for v in value):
        raise invalid("parts must be a list of: " + ", ".join(VIDEO_PARTS))
    return list(dict.fromkeys(value))


def get_videos_by_id(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"video_ids", "parts"})
    ids = _id_list(given, "video_ids", most=MAX_VIDEO_IDS)
    parts = _parts(given)
    envelope = {"count": pages.WIDEST_COUNT, "missing_ids": ids, "unread_ids": ids}
    collected = pages.Pages(False, "videos", envelope)
    returned: set[str] = set()
    unread: list[str] = []
    batches = [ids[i : i + IDS_PER_REQUEST] for i in range(0, len(ids), IDS_PER_REQUEST)]
    for index, batch in enumerate(batches):
        if index and not pages.room(context):
            unread = [i for b in batches[index:] for i in b]
            collected.warnings.append(
                pages.stop_warning(
                    f"Stopped early because time ran out; {len(unread)} IDs in unread_ids are "
                    "not read"
                )
            )
            break
        try:
            data = _read(context, "get_videos", {"part": parts, "id": batch})
        except ExtensionError as exc:
            if not index or not (pages.transient(exc) or pages.too_large_answer(exc)):
                raise
            unread = [i for b in batches[index:] for i in b]
            collected.warnings.append(
                pages.stop_warning(
                    f"YouTube could not give the next IDs ({exc.code}: {exc.message}); "
                    f"{len(unread)} IDs in unread_ids are not read"
                )
            )
            break
        items, _, _ = pages.split(data, "GET /youtube/v3/videos")
        if not collected.take(items, []):
            if not index:
                raise budget.too_large()
            unread = [i for b in batches[index:] for i in b]
            collected.warnings.append(
                pages.stop_warning(
                    f"The step output is full; {len(unread)} IDs in unread_ids are not read"
                )
            )
            break
        returned.update(
            item["id"]
            for item in items
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        )
    asked = [i for i in ids if i not in set(unread)]
    missing = [i for i in asked if i not in returned]
    return {
        "videos": collected.items,
        "count": len(collected.items),
        "missing_ids": missing,
        "unread_ids": unread,
        "warnings": collected.warnings,
    }


def get_video_processing_status(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"video_id"})
    video_id = _ident(given.get("video_id"), "video_id")
    data = _read(context, "get_videos", {"part": ["status", "processingDetails"], "id": [video_id]})
    video = _first_item(data, "GET /youtube/v3/videos", f"video {video_id}")
    status = _obj(video.get("status"))
    details = _obj(video.get("processingDetails"))
    upload_status = status.get("uploadStatus")
    processing_status = details.get("processingStatus")
    progress = details.get("processingProgress")
    warnings: list[str] = []
    if not details:
        warnings.append(
            "YouTube returned no processingDetails for this video (YouTube gives them only to "
            "the video's owner); the upload status is all that is known"
        )
    finished = processing_status in {"succeeded", "failed", "terminated"} or upload_status in {
        "processed",
        "failed",
        "rejected",
        "deleted",
    }
    return {
        "video_id": video_id,
        "upload_status": upload_status if isinstance(upload_status, str) else None,
        "processing_status": processing_status if isinstance(processing_status, str) else None,
        "privacy_status": status.get("privacyStatus")
        if isinstance(status.get("privacyStatus"), str)
        else None,
        "progress": dict(progress) if isinstance(progress, Mapping) else None,
        "failure_reason": status.get("failureReason")
        or details.get("processingFailureReason")
        or None,
        "rejection_reason": status.get("rejectionReason") or None,
        "finished": bool(finished),
        "warnings": warnings,
    }


# -- writes ------------------------------------------------------------------------------


def _write(
    context: Context,
    operation_id: str,
    given: Mapping[str, Any],
    *,
    step: str = outcome.OTHER,
    what: str = "resource",
) -> dict[str, Any]:
    """One write through a generated step, its outcome by table T."""
    entry = generic.spec(operation_id)
    plan = generic.prepare(operation_id, given)
    answer = context.transport.write(generic.to_call(entry, plan))
    return _outcome(context, entry, answer, plan.shown, step=step, what=what)


def _outcome(
    context: Context,
    entry: Mapping[str, Any],
    answer: Answer,
    shown: str,
    *,
    step: str,
    what: str,
) -> dict[str, Any]:
    return outcome.write_outcome(
        context,
        answer,
        shown,
        entry=entry,
        promised=entry["answer"] == "json",
        step=step,
        find_id=outcome.resource_id,
        what=what,
    )


def _video_fields(given: Mapping[str, Any], *, title_required: bool) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    title = given.get("title")
    if title not in (None, ""):
        fields["title"] = text(title, "title", max_length=MAX_TITLE)
    elif title_required:
        raise invalid("title is required")
    if "description" in given:
        value = given["description"]
        if not isinstance(value, str) or len(value) > MAX_DESCRIPTION:
            raise invalid(f"description must be text of at most {MAX_DESCRIPTION} characters")
        fields["description"] = value
    if "tags" in given:
        fields["tags"] = _list(given, "tags", max_items=MAX_TAGS, max_length=MAX_TAG)
    category = _opt_text(given, "category_id", max_length=MAX_CATEGORY_ID_LENGTH)
    if category is not None:
        if not category.isdigit():
            raise invalid("category_id must be a video category ID such as 22")
        fields["categoryId"] = category
    language = _opt_text(given, "default_language", max_length=MAX_LANGUAGE_LENGTH)
    if language is not None:
        fields["defaultLanguage"] = language
    return fields


def _status_fields(given: Mapping[str, Any], *, default_privacy: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    privacy = _choice(given, "privacy_status", PRIVACY, default_privacy)
    if privacy is not None:
        fields["privacyStatus"] = privacy
    publish = _publish_at(given, privacy)
    if publish is not None:
        fields["publishAt"] = publish
    kids = _flag(given, "made_for_kids")
    if kids is not None:
        fields["selfDeclaredMadeForKids"] = kids
    synthetic = _flag(given, "contains_synthetic_media")
    if synthetic is not None:
        fields["containsSyntheticMedia"] = synthetic
    embeddable = _flag(given, "embeddable")
    if embeddable is not None:
        fields["embeddable"] = embeddable
    return fields


UPLOAD_INPUTS = {
    "file",
    "content_type",
    "title",
    "description",
    "tags",
    "category_id",
    "default_language",
    "privacy_status",
    "publish_at",
    "made_for_kids",
    "contains_synthetic_media",
    "embeddable",
    "notify_subscribers",
}


def _upload_plan(given: Mapping[str, Any]) -> tuple[dict[str, Any], str, str, bool | None]:
    """The metadata, file handle, media type and notify flag of Upload video."""
    snippet = _video_fields(given, title_required=True)
    status = _status_fields(given, default_privacy="private")
    handle = given.get("file")
    if not isinstance(handle, str) or not handle.strip():
        raise invalid("file must be the workflow file of the video")
    media = generic.spec("upload_video_file")["body"]["upload"]
    kind = given.get("content_type") or "application/octet-stream"
    kind = generic._media_type(kind)
    if not generic.media_allowed(media["accept"], kind):
        raise invalid("content_type must match one of: " + ", ".join(media["accept"]))
    return (
        {"snippet": snippet, "status": status},
        handle.strip(),
        kind,
        _flag(given, "notify_subscribers"),
    )


def validate_upload_video(given: Mapping[str, Any]) -> None:
    _upload_plan(_closed(given, UPLOAD_INPUTS))


def upload_video(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, UPLOAD_INPUTS)
    metadata, handle, kind, notify = _upload_plan(given)
    entry = generic.spec("upload_video_file")
    query: list[tuple[str, str]] = [("part", "snippet"), ("part", "status")]
    if notify is not None:
        query.append(("notifySubscribers", "true" if notify else "false"))
    content, total = files.spool(context, handle, max_bytes=entry["body"]["upload"]["max_bytes"])
    shown = f"{entry['method']} {entry['path']}"
    with content:
        answer = upload.resumable(
            context,
            method=entry["method"],
            upload_path=entry["body"]["upload"]["path"],
            api=entry["api"],
            shown=shown,
            query=query,
            metadata=dumps_json(metadata).encode("utf-8"),
            content=content,
            total=total,
            content_type=kind,
        )
    out = _outcome(context, entry, answer, shown, step=outcome.CREATE, what="video")
    video = _obj(out["data"])
    status = _obj(video.get("status"))
    return {
        "video_id": out["id"],
        "upload_status": status.get("uploadStatus")
        if isinstance(status.get("uploadStatus"), str)
        else None,
        "size_bytes": total,
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


DETAIL_INPUTS = {
    "video_id",
    "title",
    "description",
    "tags",
    "category_id",
    "default_language",
    "privacy_status",
    "publish_at",
    "made_for_kids",
    "contains_synthetic_media",
    "embeddable",
}
#: Fields of the snippet and status parts that a write keeps from the current video, so
#: that sending a part does not clear them (VideoSnippet / VideoStatus @mutable fields).
SNIPPET_KEPT = ("title", "description", "tags", "categoryId", "defaultLanguage")
STATUS_KEPT = (
    "privacyStatus",
    "publishAt",
    "license",
    "embeddable",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)


def _detail_plan(given: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    video_id = _ident(given.get("video_id"), "video_id")
    snippet = _video_fields(given, title_required=False)
    status = _status_fields(given, default_privacy=None)
    if not snippet and not status:
        raise invalid("Give at least one field to change")
    return video_id, snippet, status


def validate_update_video_details(given: Mapping[str, Any]) -> None:
    _detail_plan(_closed(given, DETAIL_INPUTS))


def update_video_details(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, DETAIL_INPUTS)
    video_id, snippet, status = _detail_plan(given)
    parts = (["snippet"] if snippet else []) + (["status"] if status else [])
    data = _read(context, "get_videos", {"part": parts, "id": [video_id]})
    current = _first_item(data, "GET /youtube/v3/videos", f"video {video_id}")
    body: dict[str, Any] = {"id": video_id}
    if snippet:
        old = _obj(current.get("snippet"))
        body["snippet"] = {k: old[k] for k in SNIPPET_KEPT if k in old} | snippet
    if status:
        old = _obj(current.get("status"))
        merged = {k: old[k] for k in STATUS_KEPT if k in old} | status
        if merged.get("publishAt") and merged.get("privacyStatus") != "private":
            raise invalid("publish_at can be set only while the video is private")
        body["status"] = merged
    out = _write(context, "update_video", {"part": parts, "body": body})
    return {
        "video_id": video_id,
        "updated_parts": parts,
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


THUMBNAIL_INPUTS = {"video_id", "file", "content_type"}


def _thumbnail_plan(given: Mapping[str, Any]) -> tuple[str, str, str]:
    video_id = _ident(given.get("video_id"), "video_id")
    handle = given.get("file")
    if not isinstance(handle, str) or not handle.strip():
        raise invalid("file must be the workflow file of the image")
    kind = generic._media_type(given.get("content_type") or "image/jpeg")
    if kind not in {"image/jpeg", "image/png", "application/octet-stream"}:
        raise invalid("content_type must be image/jpeg, image/png or application/octet-stream")
    return video_id, handle.strip(), kind


def validate_set_video_thumbnail(given: Mapping[str, Any]) -> None:
    _thumbnail_plan(_closed(given, THUMBNAIL_INPUTS))


def set_video_thumbnail(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, THUMBNAIL_INPUTS)
    video_id, handle, kind = _thumbnail_plan(given)
    entry = generic.spec("set_video_thumbnail_file")
    content, total = files.spool(context, handle, max_bytes=entry["body"]["upload"]["max_bytes"])
    shown = f"{entry['method']} {entry['path']}"
    with content:
        answer = upload.resumable(
            context,
            method=entry["method"],
            upload_path=entry["body"]["upload"]["path"],
            api=entry["api"],
            shown=shown,
            query=[("videoId", video_id)],
            metadata=None,
            content=content,
            total=total,
            content_type=kind,
        )
    out = _outcome(context, entry, answer, shown, step=outcome.OTHER, what="thumbnail")
    return {
        "video_id": video_id,
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


REPLY_INPUTS = {"parent_id", "text"}


def _reply_body(given: Mapping[str, Any]) -> dict[str, Any]:
    parent = text(given.get("parent_id"), "parent_id", max_length=MAX_COMMENT_ID_LENGTH)
    if any(ch not in _ID_CHARS for ch in parent):
        raise invalid("parent_id must be a YouTube comment ID")
    value = given.get("text")
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise invalid(f"text must be the reply, 1 to {MAX_TEXT} characters")
    return {"snippet": {"parentId": parent, "textOriginal": value}}


def validate_reply_to_comment(given: Mapping[str, Any]) -> None:
    _reply_body(_closed(given, REPLY_INPUTS))


def reply_to_comment(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, REPLY_INPUTS)
    body = _reply_body(given)
    out = _write(
        context,
        "create_comment_reply",
        {"part": ["snippet"], "body": body},
        step=outcome.CREATE,
        what="reply",
    )
    return {
        "comment_id": out["id"],
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


PLAYLIST_INPUTS = {"title", "description", "privacy_status", "default_language", "tags"}


def _playlist_body(given: Mapping[str, Any]) -> dict[str, Any]:
    snippet: dict[str, Any] = {"title": text(given.get("title"), "title", max_length=MAX_TITLE)}
    if "description" in given:
        value = given["description"]
        if not isinstance(value, str) or len(value) > MAX_DESCRIPTION:
            raise invalid(f"description must be text of at most {MAX_DESCRIPTION} characters")
        snippet["description"] = value
    if "tags" in given:
        snippet["tags"] = _list(given, "tags", max_items=MAX_TAGS, max_length=MAX_TAG)
    language = _opt_text(given, "default_language", max_length=MAX_LANGUAGE_LENGTH)
    if language is not None:
        snippet["defaultLanguage"] = language
    privacy = _choice(given, "privacy_status", PRIVACY, "private")
    return {"snippet": snippet, "status": {"privacyStatus": privacy}}


def validate_create_playlist(given: Mapping[str, Any]) -> None:
    _playlist_body(_closed(given, PLAYLIST_INPUTS))


def create_playlist(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, PLAYLIST_INPUTS)
    body = _playlist_body(given)
    out = _write(
        context,
        "create_playlist_from_body",
        {"part": ["snippet", "status"], "body": body},
        step=outcome.CREATE,
        what="playlist",
    )
    return {
        "playlist_id": out["id"],
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


ADD_INPUTS = {"playlist_id", "video_id", "position"}


def _add_body(given: Mapping[str, Any]) -> dict[str, Any]:
    snippet: dict[str, Any] = {
        "playlistId": _ident(given.get("playlist_id"), "playlist_id"),
        "resourceId": {
            "kind": "youtube#video",
            "videoId": _ident(given.get("video_id"), "video_id"),
        },
    }
    if given.get("position") not in (None, ""):
        snippet["position"] = integer(
            {"minimum": 0, "maximum": 1_000_000}, given["position"], "position"
        )
    return {"snippet": snippet}


def validate_add_video_to_playlist(given: Mapping[str, Any]) -> None:
    _add_body(_closed(given, ADD_INPUTS))


def add_video_to_playlist(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, ADD_INPUTS)
    body = _add_body(given)
    out = _write(
        context,
        "create_playlist_item",
        {"part": ["snippet"], "body": body},
        step=outcome.CREATE,
        what="playlist item",
    )
    return {
        "playlist_item_id": out["id"],
        "data": out["data"],
        "processing": out["processing"],
        "applied": out["applied"],
        "check": out["check"],
        "warnings": out["warnings"],
    }


#: Everyday step id -> runner.
COMPOSITES: dict[str, Callable[[Context], dict[str, Any]]] = {
    "test_connection": test_connection,
    "list_my_channels": list_my_channels,
    "list_channel_videos": list_channel_videos,
    "get_videos_by_id": get_videos_by_id,
    "upload_video": upload_video,
    "get_video_processing_status": get_video_processing_status,
    "update_video_details": update_video_details,
    "set_video_thumbnail": set_video_thumbnail,
    "list_video_comments": list_video_comments,
    "reply_to_comment": reply_to_comment,
    "list_my_playlists": list_my_playlists,
    "create_playlist": create_playlist,
    "add_video_to_playlist": add_video_to_playlist,
    "verify_identity": verify_identity,
}
#: Everyday steps that change data in YouTube.
COMPOSITE_WRITES: frozenset[str] = frozenset(
    {
        "upload_video",
        "update_video_details",
        "set_video_thumbnail",
        "reply_to_comment",
        "create_playlist",
        "add_video_to_playlist",
    }
)
#: Input checks of the writes, run before anything is sent and in a test run.
VALIDATORS: dict[str, Callable[[Mapping[str, Any]], None]] = {
    "upload_video": validate_upload_video,
    "update_video_details": validate_update_video_details,
    "set_video_thumbnail": validate_set_video_thumbnail,
    "reply_to_comment": validate_reply_to_comment,
    "create_playlist": validate_create_playlist,
    "add_video_to_playlist": validate_add_video_to_playlist,
}
#: The outputs of each write in a test run (besides the effect facts).
NEUTRAL: dict[str, dict[str, Any]] = {
    "upload_video": {"video_id": None, "upload_status": None, "size_bytes": None, "data": None},
    "update_video_details": {"video_id": None, "updated_parts": [], "data": None},
    "set_video_thumbnail": {"video_id": None, "data": None},
    "reply_to_comment": {"comment_id": None, "data": None},
    "create_playlist": {"playlist_id": None, "data": None},
    "add_video_to_playlist": {"playlist_item_id": None, "data": None},
}

__all__ = ["COMPOSITES", "COMPOSITE_WRITES", "NEUTRAL", "VALIDATORS"]
