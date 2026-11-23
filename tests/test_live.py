"""Read-only checks against the real YouTube APIs.

They run only when ``YOUTUBE_TOKEN_FILE`` names a file holding a current OAuth access token
of a test channel (scopes of the connection type YouTube channel); otherwise they are
skipped. They only read: nothing is changed on the channel.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from support import payload

from runtime.operations import handle_runtime

TOKEN_FILE = os.environ.get("YOUTUBE_TOKEN_FILE", "")

pytestmark = pytest.mark.skipif(
    not TOKEN_FILE or not Path(TOKEN_FILE).is_file(),
    reason="set YOUTUBE_TOKEN_FILE to a file with a YouTube access token to run the live reads",
)


def live(operation_id: str, given: dict[str, Any] | None = None) -> dict[str, Any]:
    token = Path(TOKEN_FILE).read_text(encoding="utf-8").strip()
    response = handle_runtime(payload(operation_id, given or {}, token=token))
    assert token not in json.dumps(response, default=str)
    return response


def test_live_the_connection_names_a_channel() -> None:
    response = live("test_connection")
    assert response["ok"] is True, response
    assert response["result"]["channel_id"].startswith("UC")


def test_live_my_channels_and_their_videos() -> None:
    channels = live("list_my_channels")
    assert channels["ok"] is True, channels
    assert channels["result"]["count"] >= 1
    videos = live("list_channel_videos", {"max_videos": 5})
    assert videos["ok"] is True, videos
    assert videos["result"]["count"] <= 5 or videos["result"]["complete"] is False


def test_live_a_generated_read() -> None:
    response = live("get_video_categories", {"part": ["snippet"], "region_code": "US"})
    assert response["ok"] is True, response
