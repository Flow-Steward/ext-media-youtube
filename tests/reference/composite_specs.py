"""The everyday steps: their inputs, outputs and descriptions.

They are built on top of the generated steps (runtime/composites.py) and come first in
the step list. Contract files are generated from this module by build_contracts.py.
"""

from __future__ import annotations

from typing import Any

PRIVACY = ["private", "unlisted", "public"]
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

WARNINGS = {
    "name": "warnings",
    "type": "array",
    "items": {"type": "string"},
    "description": "What the step could not do fully or what to check.",
}

#: The outputs every write returns about what YouTube's answer confirms.
PROCESSING_OUTPUTS: list[dict[str, Any]] = [
    {
        "name": "processing",
        "type": ["string", "null"],
        "enum": ["completed", "accepted", None],
        "description": (
            "completed: YouTube answered that the change is made. accepted: YouTube took the "
            "uploaded video and processes it afterwards; check the outcome with the step "
            "named in check. None in a test run and when nothing was sent."
        ),
    },
    {
        "name": "applied",
        "type": ["boolean", "null"],
        "description": (
            "True with processing completed. False with processing accepted (read the outcome "
            "with the check step), in a test run and when nothing was sent."
        ),
    },
    {
        "name": "check",
        "type": ["object", "null"],
        "additionalProperties": True,
        "description": (
            "With processing accepted: operation_id, the step that reads the outcome. None "
            "otherwise."
        ),
    },
]

NEXT_SKIP: dict[str, Any] = {
    "name": "next_skip",
    "type": ["integer", "null"],
    "description": (
        "When complete is false: the skip to start the next run with, together with "
        "next_page_token (records of that page already returned)."
    ),
}
#: The outputs of a list step.
PAGE_OUTPUTS: list[dict[str, Any]] = [
    {
        "name": "items",
        "type": "array",
        "items": {"type": "object", "additionalProperties": True},
        "description": "The records read.",
    },
    {"name": "count", "type": "integer", "description": "How many records were read."},
    {
        "name": "complete",
        "type": "boolean",
        "description": "True when the list was read to its end.",
    },
    {
        "name": "next_page_token",
        "type": ["string", "null"],
        "description": "When complete is false: the page_token to start the next run from.",
    },
    NEXT_SKIP,
]

EFFECT_OUTPUTS: list[dict[str, Any]] = [
    {"name": "external_effect_status", "type": "string"},
    {"name": "definitely_no_external_effect", "type": "boolean"},
]


def _text(name: str, title: str, description: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "title": title, "description": description, "type": "string", **extra}


def _list_outputs(key: str, what: str, *, to_file: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "name": key,
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
            "description": f"The {what} read"
            + (" (empty with output file: they are in file)." if to_file else "."),
        },
        {"name": "count", "type": "integer", "description": f"How many {what} were read."},
        {
            "name": "complete",
            "type": "boolean",
            "description": f"True when all {what} were read.",
        },
        {
            "name": "next_page_token",
            "type": ["string", "null"],
            "description": "When complete is false: the page_token to start the next run from.",
        },
        NEXT_SKIP,
    ]
    if to_file:
        rows.append(
            {
                "name": "file",
                "type": ["string", "null"],
                "value_type": "artifact_handle",
                "description": f"With output file: the {what} as a JSON workflow file.",
            }
        )
    return rows


PAGE_TOKEN = _text(
    "page_token",
    "Page token",
    "Start from this page: next_page_token of an earlier run that stopped early.",
    maxLength=1000,
)
SKIP: dict[str, Any] = {
    "name": "skip",
    "title": "Skip",
    "type": "integer",
    "minimum": 0,
    "maximum": 100000,
    "description": (
        "With page_token: how many records of that page the earlier run already returned "
        "(its next_skip)."
    ),
}
OUTPUT = _text(
    "output",
    "Output",
    "step (default): the records in the step output. file: a JSON workflow file, for long lists.",
    enum=["step", "file"],
)
VIDEO_ID = _text("video_id", "Video ID", "The YouTube video ID.", maxLength=100, required=True)
DATA = {
    "name": "data",
    "type": ["object", "null"],
    "additionalProperties": True,
    "description": "The resource YouTube returned.",
}
TITLE = _text("title", "Title", "The title.", maxLength=1000)
DESCRIPTION = _text(
    "description", "Description", "The description (an empty text clears it).", maxLength=20000
)
TAGS = {
    "name": "tags",
    "title": "Tags",
    "type": "array",
    "items": {"type": "string", "maxLength": 500},
    "maxItems": 500,
    "description": "Keyword tags (they replace the current ones).",
}
CATEGORY = _text(
    "category_id",
    "Category ID",
    "The video category ID, such as 22 (Get video categories lists them).",
    maxLength=20,
)
LANGUAGE = _text(
    "default_language",
    "Default language",
    "The language of the title and description.",
    maxLength=35,
)
PRIVACY_INPUT = _text("privacy_status", "Privacy", "private, unlisted or public.", enum=PRIVACY)
PUBLISH_AT = _text(
    "publish_at",
    "Publish at",
    "When YouTube publishes the video, such as 2026-12-01T09:00:00Z; only with privacy private.",
    maxLength=40,
)
KIDS = {
    "name": "made_for_kids",
    "title": "Made for kids",
    "type": "boolean",
    "description": "Whether the video is made for kids (selfDeclaredMadeForKids).",
}
SYNTHETIC = {
    "name": "contains_synthetic_media",
    "title": "Contains altered or synthetic media",
    "type": "boolean",
    "description": "Whether the video contains altered or synthetic media.",
}
EMBEDDABLE = {
    "name": "embeddable",
    "title": "Embeddable",
    "type": "boolean",
    "description": "Whether the video can be embedded on other websites.",
}

VERIFY_IDENTITY = {
    "action_id": "verify_identity",
    "title": "Verify YouTube channel",
    "description": (
        "Run by Flow Steward after a new authorization: reads the channel of the connected "
        "Google account (GET /youtube/v3/channels, mine) and returns its id and title."
    ),
}


def _write(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return outputs + PROCESSING_OUTPUTS + [WARNINGS] + EFFECT_OUTPUTS


COMPOSITES: list[dict[str, Any]] = [
    {
        "operation_id": "test_connection",
        "title": "Test connection",
        "kind": "read",
        "calls": ["GET /youtube/v3/channels"],
        "description": (
            "Checks that YouTube accepts the connection's authorization by reading the channel "
            "it belongs to (channels.list with mine). Returns the channel ID, title and handle. "
            "Quota cost: 1 unit."
        ),
        "inputs": [],
        "outputs": [
            {
                "name": "connected",
                "type": "boolean",
                "description": "True when YouTube accepted the authorization.",
            },
            {"name": "channel_id", "type": ["string", "null"], "description": "The channel ID."},
            {"name": "title", "type": ["string", "null"], "description": "The channel title."},
            {
                "name": "custom_url",
                "type": ["string", "null"],
                "description": "The channel's handle (customUrl), when it has one.",
            },
            {
                "name": "connection_type",
                "type": "string",
                "description": "The connection type, which decides the Google scopes.",
            },
            WARNINGS,
        ],
    },
    {
        "operation_id": "list_my_channels",
        "title": "Get my channels",
        "kind": "read",
        "calls": ["GET /youtube/v3/channels"],
        "description": (
            "Reads the channels of the connected account with their snippet, statistics "
            "(views, subscribers, videos), content details (the uploads playlist) and status, "
            "all pages. Quota cost: 1 unit per page."
        ),
        "inputs": [],
        "outputs": _list_outputs("channels", "channels", to_file=False) + [WARNINGS],
    },
    {
        "operation_id": "list_channel_videos",
        "title": "Get all channel videos",
        "kind": "read",
        "calls": ["GET /youtube/v3/channels", "GET /youtube/v3/playlistItems"],
        "description": (
            "Reads every video of a channel (the connected one when channel_id is empty) "
            "through its uploads playlist, 50 per page, until all are read or max_videos, the "
            "step output (or with output file a JSON workflow file) is full or time runs out; "
            "then complete is false and next_page_token says where to continue. Each record is "
            "a playlist item with the video ID in contentDetails.videoId. Quota cost: 1 unit "
            "per page plus 1 for the channel."
        ),
        "inputs": [
            _text(
                "channel_id",
                "Channel ID",
                "The channel; empty: the connected channel.",
                maxLength=100,
            ),
            {
                "name": "max_videos",
                "title": "Most videos",
                "type": "integer",
                "minimum": 1,
                "maximum": 50000,
                "description": "The most videos to read (default 5000).",
            },
            PAGE_TOKEN,
            SKIP,
            OUTPUT,
        ],
        "outputs": [
            {
                "name": "channel_id",
                "type": ["string", "null"],
                "description": "The channel read.",
            },
            {
                "name": "uploads_playlist_id",
                "type": "string",
                "description": "The channel's uploads playlist.",
            },
        ]
        + _list_outputs("videos", "videos", to_file=True)
        + [WARNINGS],
    },
    {
        "operation_id": "get_videos_by_id",
        "title": "Get videos by ID",
        "kind": "read",
        "calls": ["GET /youtube/v3/videos"],
        "description": (
            "Reads videos by ID, 50 per request, with the parts asked for (default snippet, "
            "contentDetails, statistics and status). IDs YouTube does not return are in "
            "missing_ids; IDs not read because the output is full or time ran out are in "
            "unread_ids. Quota cost: 1 unit per 50 IDs."
        ),
        "inputs": [
            {
                "name": "video_ids",
                "title": "Video IDs",
                "type": "array",
                "items": {"type": "string", "maxLength": 100},
                "minItems": 1,
                "maxItems": 5000,
                "required": True,
                "description": "The YouTube video IDs (up to 5000).",
            },
            {
                "name": "parts",
                "title": "Parts",
                "type": "array",
                "items": {"type": "string", "enum": VIDEO_PARTS},
                "maxItems": len(VIDEO_PARTS),
                "description": "The video parts to read; default snippet, contentDetails, statistics, status.",
            },
        ],
        "outputs": [
            {
                "name": "videos",
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
                "description": "The videos YouTube returned.",
            },
            {"name": "count", "type": "integer", "description": "How many videos were returned."},
            {
                "name": "missing_ids",
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs asked for that YouTube did not return (deleted, private or wrong).",
            },
            {
                "name": "unread_ids",
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs not read because the output was full or time ran out; read them in a next run.",
            },
            WARNINGS,
        ],
    },
    {
        "operation_id": "upload_video",
        "title": "Upload video",
        "kind": "write",
        "calls": ["POST /upload/youtube/v3/videos", "PUT (upload session)"],
        "upload": {
            "accept": ["video/*", "application/octet-stream"],
            "max_bytes": 200 * 1024 * 1024,
        },
        "description": (
            "Uploads a video from a workflow file (up to 200 MiB, the Flow Steward default for "
            "a workflow file; YouTube allows 256 GiB) with YouTube's resumable upload, with "
            "its title, description, tags, category and privacy (default private). YouTube "
            "processes the video afterwards: the step returns the new video_id with processing "
            "accepted and applied false; read the outcome with Get video processing status. "
            'Quota (YouTube\'s quota table): "100 quota per day. Each call costs 1 quota."'
        ),
        "inputs": [
            {
                "name": "file",
                "title": "Video file",
                "value_type": "artifact_handle",
                "required": True,
                "description": "The workflow file of the video, up to 200 MiB.",
            },
            _text(
                "content_type",
                "File type",
                "The video's media type, such as video/mp4. Default: application/octet-stream.",
                maxLength=100,
            ),
            {**TITLE, "required": True},
            DESCRIPTION,
            TAGS,
            CATEGORY,
            LANGUAGE,
            {**PRIVACY_INPUT, "description": "private (default), unlisted or public."},
            PUBLISH_AT,
            KIDS,
            SYNTHETIC,
            EMBEDDABLE,
            {
                "name": "notify_subscribers",
                "title": "Notify subscribers",
                "type": "boolean",
                "description": "Whether YouTube notifies the channel's subscribers (YouTube's default: yes).",
            },
        ],
        "outputs": _write(
            [
                {
                    "name": "video_id",
                    "type": ["string", "null"],
                    "description": "The new video's ID.",
                },
                {
                    "name": "upload_status",
                    "type": ["string", "null"],
                    "description": "status.uploadStatus YouTube returned, such as uploaded.",
                },
                {
                    "name": "size_bytes",
                    "type": ["integer", "null"],
                    "description": "The size of the uploaded file.",
                },
                DATA,
            ]
        ),
    },
    {
        "operation_id": "get_video_processing_status",
        "title": "Get video processing status",
        "kind": "read",
        "calls": ["GET /youtube/v3/videos"],
        "description": (
            "Reads how far YouTube got with an uploaded video: status.uploadStatus and, for "
            "the video's owner, processingDetails (processing status, progress, failure "
            "reason). finished is true once YouTube processed, failed, rejected or deleted it. "
            "Quota cost: 1 unit."
        ),
        "inputs": [VIDEO_ID],
        "outputs": [
            {"name": "video_id", "type": "string", "description": "The video."},
            {
                "name": "upload_status",
                "type": ["string", "null"],
                "description": "uploaded, processed, failed, rejected or deleted.",
            },
            {
                "name": "processing_status",
                "type": ["string", "null"],
                "description": "processing, succeeded, failed or terminated (owner only).",
            },
            {
                "name": "privacy_status",
                "type": ["string", "null"],
                "description": "private, unlisted or public.",
            },
            {
                "name": "progress",
                "type": ["object", "null"],
                "additionalProperties": True,
                "description": "processingProgress: partsTotal, partsProcessed, timeLeftMs.",
            },
            {
                "name": "failure_reason",
                "type": ["string", "null"],
                "description": "Why the upload or processing failed.",
            },
            {
                "name": "rejection_reason",
                "type": ["string", "null"],
                "description": "Why YouTube rejected the video.",
            },
            {
                "name": "finished",
                "type": "boolean",
                "description": "True when YouTube has finished with the video, either way.",
            },
            WARNINGS,
        ],
    },
    {
        "operation_id": "update_video_details",
        "title": "Update video details",
        "kind": "write",
        "calls": ["GET /youtube/v3/videos", "PUT /youtube/v3/videos"],
        "description": (
            "Changes a video's title, description, tags, category, language, privacy, "
            "publishing time or audience. It reads the video first and sends the snippet and "
            "status parts with the fields not given kept as they are, because YouTube clears "
            "what a sent part leaves out. Quota cost: 1 unit to read, 50 to update."
        ),
        "inputs": [
            VIDEO_ID,
            TITLE,
            DESCRIPTION,
            TAGS,
            CATEGORY,
            LANGUAGE,
            PRIVACY_INPUT,
            PUBLISH_AT,
            KIDS,
            SYNTHETIC,
            EMBEDDABLE,
        ],
        "outputs": _write(
            [
                {"name": "video_id", "type": ["string", "null"], "description": "The video."},
                {
                    "name": "updated_parts",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The parts sent: snippet, status or both.",
                },
                DATA,
            ]
        ),
    },
    {
        "operation_id": "set_video_thumbnail",
        "title": "Set video thumbnail",
        "kind": "write",
        "calls": ["POST /upload/youtube/v3/thumbnails/set", "PUT (upload session)"],
        "upload": {
            "accept": ["image/jpeg", "image/png", "application/octet-stream"],
            "max_bytes": 50 * 1024 * 1024,
        },
        "description": (
            "Uploads a JPEG or PNG from a workflow file as a video's custom thumbnail. Quota "
            "cost: 50 units."
        ),
        "inputs": [
            VIDEO_ID,
            {
                "name": "file",
                "title": "Image file",
                "value_type": "artifact_handle",
                "required": True,
                "description": "The workflow file of the image (JPEG or PNG).",
            },
            _text(
                "content_type",
                "File type",
                "image/jpeg (default), image/png or application/octet-stream.",
                enum=["image/jpeg", "image/png", "application/octet-stream"],
            ),
        ],
        "outputs": _write(
            [{"name": "video_id", "type": ["string", "null"], "description": "The video."}, DATA]
        ),
    },
    {
        "operation_id": "list_video_comments",
        "title": "Get all video comments",
        "kind": "read",
        "calls": ["GET /youtube/v3/commentThreads"],
        "description": (
            "Reads every top-level comment of a video, 100 per page, optionally with the "
            "replies YouTube includes in a thread, until all are read or max_comments, the "
            "step output (or with output file a JSON workflow file) is full or time runs out; "
            "then complete is false and next_page_token says where to continue. Quota cost: "
            "1 unit per page."
        ),
        "inputs": [
            VIDEO_ID,
            _text(
                "order", "Order", "time (newest first) or relevance.", enum=["time", "relevance"]
            ),
            _text("search_terms", "Search", "Only comments containing these words.", maxLength=500),
            _text(
                "text_format",
                "Text format",
                "html (YouTube's default) or plainText.",
                enum=["html", "plainText"],
            ),
            {
                "name": "include_replies",
                "title": "Include replies",
                "type": "boolean",
                "description": "Also return the replies YouTube includes in each thread (Get comments reads all replies of one comment).",
            },
            {
                "name": "max_comments",
                "title": "Most comments",
                "type": "integer",
                "minimum": 1,
                "maximum": 100000,
                "description": "The most comment threads to read (default 10000).",
            },
            PAGE_TOKEN,
            SKIP,
            OUTPUT,
        ],
        "outputs": _list_outputs("comments", "comment threads", to_file=True) + [WARNINGS],
    },
    {
        "operation_id": "reply_to_comment",
        "title": "Reply to comment",
        "kind": "write",
        "calls": ["POST /youtube/v3/comments"],
        "description": (
            "Posts a reply to a comment as the connected channel. Returns the new comment_id. "
            "Quota cost: 50 units."
        ),
        "inputs": [
            _text(
                "parent_id",
                "Comment ID",
                "The ID of the top-level comment to reply to.",
                maxLength=200,
                required=True,
            ),
            _text("text", "Reply", "The text of the reply.", maxLength=20000, required=True),
        ],
        "outputs": _write(
            [
                {
                    "name": "comment_id",
                    "type": ["string", "null"],
                    "description": "The new reply's ID.",
                },
                DATA,
            ]
        ),
    },
    {
        "operation_id": "list_my_playlists",
        "title": "Get all my playlists",
        "kind": "read",
        "calls": ["GET /youtube/v3/playlists"],
        "description": (
            "Reads every playlist of the connected channel with its snippet, item count and "
            "privacy, 50 per page, until all are read or max_playlists; then complete is "
            "false and next_page_token says where to continue. Quota cost: 1 unit per page."
        ),
        "inputs": [
            {
                "name": "max_playlists",
                "title": "Most playlists",
                "type": "integer",
                "minimum": 1,
                "maximum": 50000,
                "description": "The most playlists to read (default 5000).",
            },
            PAGE_TOKEN,
            SKIP,
        ],
        "outputs": _list_outputs("playlists", "playlists", to_file=False) + [WARNINGS],
    },
    {
        "operation_id": "create_playlist",
        "title": "Create playlist",
        "kind": "write",
        "calls": ["POST /youtube/v3/playlists"],
        "description": (
            "Creates a playlist on the connected channel with a title, description, tags and "
            "privacy (default private). Returns the new playlist_id. Quota cost: 50 units."
        ),
        "inputs": [
            {**TITLE, "required": True},
            DESCRIPTION,
            {**PRIVACY_INPUT, "description": "private (default), unlisted or public."},
            LANGUAGE,
            TAGS,
        ],
        "outputs": _write(
            [
                {
                    "name": "playlist_id",
                    "type": ["string", "null"],
                    "description": "The new playlist's ID.",
                },
                DATA,
            ]
        ),
    },
    {
        "operation_id": "add_video_to_playlist",
        "title": "Add video to playlist",
        "kind": "write",
        "calls": ["POST /youtube/v3/playlistItems"],
        "description": (
            "Adds a video to a playlist, at the end or at a position (0 is the first). "
            "Returns the new playlist_item_id. Quota cost: 50 units."
        ),
        "inputs": [
            _text("playlist_id", "Playlist ID", "The playlist.", maxLength=100, required=True),
            VIDEO_ID,
            {
                "name": "position",
                "title": "Position",
                "type": "integer",
                "minimum": 0,
                "maximum": 1000000,
                "description": "Where in the playlist, 0 for the first; empty: at the end.",
            },
        ],
        "outputs": _write(
            [
                {
                    "name": "playlist_item_id",
                    "type": ["string", "null"],
                    "description": "The new playlist item's ID.",
                },
                DATA,
            ]
        ),
    },
]
