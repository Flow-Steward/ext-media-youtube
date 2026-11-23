"""The pinned sources are the downloaded ones, and the quota facts are extracted from the
pinned documentation page."""

from __future__ import annotations

import hashlib
import json
import sys

import pytest
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402
import extract_quota  # noqa: E402


@pytest.mark.parametrize("api", sorted(build_contracts.SOURCES))
def test_each_discovery_document_is_the_pinned_one(api: str) -> None:
    pin = build_contracts.SOURCES[api]
    raw = (BUNDLE / "tests" / "reference" / pin["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["sha256"]
    assert len(raw) == pin["bytes"]
    assert pin["downloaded"] == "2026-11-23"


def test_the_pinned_documents_are_what_they_say() -> None:
    facts = build_contracts.sources_facts()
    assert facts["data"]["name"] == "youtube" and facts["data"]["version"] == "v3"
    assert facts["data"]["revision"] == "20261119"
    assert facts["data"]["root_url"] == "https://youtube.googleapis.com/"


def test_a_changed_document_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "youtube_v3.json").write_text("{}")
    monkeypatch.setattr(build_contracts, "HERE", tmp_path)
    with pytest.raises(SystemExit, match="not the pinned document"):
        build_contracts.document("data")


@pytest.mark.skipif(
    not extract_quota.SOURCE.exists(), reason="the documentation page is not committed"
)
def test_the_quota_facts_are_extracted_from_the_pinned_page() -> None:
    assert extract_quota.extract(extract_quota.SOURCE.read_bytes()) == json.loads(
        extract_quota.OUTPUT.read_text(encoding="utf-8")
    )


def test_a_changed_quota_page_is_refused() -> None:
    with pytest.raises(SystemExit, match="the documentation page changed"):
        extract_quota.extract(b"<html></html>")


def test_the_quota_pin_is_the_downloaded_one() -> None:
    source = build_contracts.quota()["source"]
    assert source["sha256"] == extract_quota.SHA256
    assert source["bytes"] == extract_quota.BYTES == 142880
    assert source["downloaded"] == "2026-11-23" and source["last_updated"] == "2026-11-12"
    assert source["url"] == "https://developers.google.com/youtube/data/determine_quota_cost?hl=en"
    costs = build_contracts.quota()["costs"]
    assert len(costs) == 71
    assert costs["videos.list"] == "1" and costs["captions.update"] == "450"
