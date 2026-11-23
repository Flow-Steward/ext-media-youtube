"""The generated contracts match their sources; every method of the source is a step or an
exclusion with its reason; forms, inputs and the runtime agree; the extension's standing
rules (ids, names, outputs, OAuth, UI, icon, version) hold."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import struct
import sys
from typing import Any

import pytest
import yaml
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402
import composite_specs  # noqa: E402
import names  # noqa: E402

from runtime import catalog, composites, files, generic, limits, upload  # noqa: E402

OUTPUTS = build_contracts.outputs()
EVERYDAY = [c["operation_id"] for c in composite_specs.COMPOSITES]
REPOSITORY = "https://github.com/Flow-Steward/ext-media-youtube"


def load(path: str) -> Any:
    return yaml.safe_load((BUNDLE / path).read_text(encoding="utf-8"))


def operations() -> list[dict[str, Any]]:
    return load("contracts/operation_manifest.yaml")["operations"]


def source_methods() -> dict[str, dict[str, Any]]:
    return {m["id"]: m for _, m in build_contracts.all_methods()}


@pytest.mark.parametrize("path", sorted(OUTPUTS))
def test_generated_files_are_current(path: str) -> None:
    assert (BUNDLE / path).read_text(encoding="utf-8") == build_contracts.render(
        path, OUTPUTS[path]
    ), f"{path} drifted: run python3 tests/reference/build_contracts.py"


def test_every_method_of_the_source_is_a_step_or_excluded_with_a_reason() -> None:
    methods = source_methods()
    assert len(build_contracts.methods("data")) == 83
    assert len(build_contracts.methods("analytics")) == 8
    registry = generic.registry()
    covered = {e["vendor_method_id"] for e in registry.values()}
    excluded = set(names.EXCLUDED)
    assert covered | excluded == set(methods)
    assert not covered & excluded
    assert excluded == {"youtube.tests.insert", "youtube.youtube.v3.liveChat.messages.stream"}
    for method_id, reason in names.EXCLUDED.items():
        assert len(reason) > 40, method_id
    assert registry_counts(registry) == {"GET": 31, "POST": 30, "PUT": 12, "DELETE": 16}
    assert len(registry) == 89
    manifest = [o["operation_id"] for o in operations()]
    assert manifest[: len(EVERYDAY)] == EVERYDAY
    assert sorted(manifest[len(EVERYDAY) :]) == sorted(registry) and len(manifest) == 103
    assert set(manifest) | {"verify_identity"} == set(catalog.OPERATION_IDS)
    assert set(names.TITLES) == covered


def registry_counts(registry: dict[str, Any]) -> dict[str, int]:
    return dict(collections.Counter(e["method"] for e in registry.values()))


def test_the_coverage_page_lists_the_exclusions_and_the_reporting_api() -> None:
    body = load("ui/pages/coverage.yaml")["components"][0]["body"]
    for method_id in names.EXCLUDED:
        assert method_id in body
    assert "YouTube Reporting API" in body
    assert "89 of them have their own step" in body


def test_step_ids_are_frozen_unique_and_never_vendor_ids() -> None:
    ids = json.loads((BUNDLE / "tests/reference/step_ids.json").read_text())
    assert set(ids) == set(source_methods()) - set(names.EXCLUDED)
    values = list(ids.values()) + EVERYDAY + ["verify_identity"]
    assert len(values) == len(set(values))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]{2,80}", v) for v in values)
    assert set(generic.registry()) == set(ids.values())
    assert not set(source_methods()) & set(values)


def test_titles_are_verb_first_and_unique() -> None:
    titles = [o["display_name"] for o in operations()]
    assert len(titles) == len(set(titles))
    for title in titles:
        assert title.split()[0] in names.VERBS, title


def test_everyday_steps_come_first_and_reads_precede_deletes_within_a_resource() -> None:
    ids = [o["operation_id"] for o in operations()]
    assert ids[: len(EVERYDAY)] == EVERYDAY
    registry = generic.registry()
    by_resource: dict[str, list[str]] = collections.defaultdict(list)
    for oid in ids[len(EVERYDAY) :]:
        by_resource[registry[oid]["resource"]].append(registry[oid]["method"])
    for resource, methods in by_resource.items():
        if "GET" in methods:
            assert methods[0] == "GET", resource
        if "DELETE" in methods:
            assert methods[-1] == "DELETE", resource


def test_every_step_has_warnings_and_every_write_is_a_suppressed_effect() -> None:
    effects = load("extension.yaml")["external_effects"]
    effect_ids = {e["operation_id"] for e in effects}
    for op in operations():
        names_out = [o["name"] for o in op["outputs"]]
        assert "warnings" in names_out, op["operation_id"]
        write = op["operation_kind"] == "action"
        assert write == (op["operation_id"] in effect_ids)
        assert write == (op["operation_id"] in catalog.EFFECT_OPERATION_IDS)
        if write:
            assert {
                "external_effect_status",
                "definitely_no_external_effect",
                "processing",
                "applied",
                "check",
            } <= set(names_out)
            assert "timeout_unknown" in op["error_codes"]
    generated_writes = {k for k, v in generic.registry().items() if v["kind"] == "write"}
    assert generated_writes | composites.COMPOSITE_WRITES == effect_ids
    assert len(effect_ids) == 58 + 6
    assert all(
        e["idempotency"] == "required" and e["test_mode_behavior"] == "suppress" for e in effects
    )


def test_reads_are_exactly_the_get_methods() -> None:
    for oid, entry in generic.registry().items():
        assert (entry["kind"] == "read") == (entry["method"] == "GET"), oid


def test_forms_inputs_and_runtime_agree() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/step_ui_manifest.yaml")["forms"]}
    actions = {a["action_id"]: a for a in load("ui/actions/actions.yaml")["actions"]}
    registry = generic.registry()
    for op in operations():
        oid = op["operation_id"]
        inputs = [i["name"] for i in op["inputs"] if i["name"] != "connection_ref"]
        assert [f["name"] for f in forms[oid]["fields"]] == inputs, oid
        assert [p["name"] for p in actions[oid]["parameters"]] == ["connection_ref", *inputs]
        if oid in registry:
            assert set(inputs) == generic.inputs_of(registry[oid]), oid
        for item in op["inputs"]:
            if item["value_type"] == "artifact_handle":
                field = next(f for f in forms[oid]["fields"] if f["name"] == item["name"])
                assert field["widget_type"] == "artifact_picker"


def test_every_everyday_step_refuses_inputs_it_does_not_declare() -> None:
    from support import FakeYouTube, run

    for spec in composite_specs.COMPOSITES:
        fake = FakeYouTube()
        result = run(spec["operation_id"], {"surely_unknown": 1}, fake, test_mode=True)
        assert result["error_code"] == "invalid_payload", spec["operation_id"]
        assert "surely_unknown" in result["error"] and fake.calls == []


def test_the_post_connect_action_has_the_closed_automatic_profile() -> None:
    action = next(
        a for a in load("ui/actions/actions.yaml")["actions"] if a["action_id"] == "verify_identity"
    )
    assert action["workflow_visible"] is False and action["parameters"] == []
    assert action["mutates_platform"] is False and action["handler"] == {"mode": "extension"}
    assert "verify_identity" not in {o["operation_id"] for o in operations()}
    effects = {e["operation_id"] for e in load("extension.yaml")["external_effects"]}
    assert "verify_identity" not in effects


def test_oauth_is_declared_like_the_flow_steward_google_workspace_extension() -> None:
    providers = load("extension.yaml")["runtime"]["extension_contract_v2"]["oauth_providers"]
    assert [p["provider_id"] for p in providers] == ["google_youtube"]
    provider = providers[0]
    assert provider["flow"] == {"type": "authorization_code", "pkce": "s256"}
    assert provider["authorization_endpoint"] == {
        "url": "https://accounts.google.com/o/oauth2/v2/auth"
    }
    assert provider["token_endpoint"] == {
        "url": "https://oauth2.googleapis.com/token",
        "client_auth_method": "client_secret_post",
    }
    assert provider["revocation_endpoint"] == {"url": "https://oauth2.googleapis.com/revoke"}
    assert provider["callback_id"] == "oauth_authorization"
    assert provider["post_connect_action_id"] == "verify_identity"
    intent = provider["authorization_intents"][0]
    assert intent["static_parameters"] == {
        "access_type": "offline",
        "include_granted_scopes": False,
        "prompt": "consent select_account",
    }
    fields = {f["field_id"]: f for f in provider["credential_fields"]}
    assert set(fields) == {"client_id", "client_secret"}
    assert fields["client_secret"]["secret"] is True and fields["client_id"]["secret"] is False
    callbacks = load("extension.yaml")["callbacks"]
    assert callbacks == [
        {
            "callback_id": "oauth_authorization",
            "purpose": "oauth_authorization",
            "methods": ["GET"],
            "connection_scoped": False,
        }
    ]


def test_connection_types_ask_for_scopes_the_source_names() -> None:
    types = load("contracts/connection_types.yaml")["connection_types"]
    assert [t["connection_type_id"] for t in types] == [
        "youtube_channel",
        "youtube_channel_monetized",
        "youtube_content_owner",
    ]
    known: set[str] = set()
    for api in build_contracts.SOURCES:
        known |= set(build_contracts.document(api)["auth"]["oauth2"]["scopes"])
    for row in types:
        auth = row["auth"]
        assert auth["type"] == "oauth2" and auth["provider_id"] == "google_youtube"
        assert set(auth["scopes"]["required"]) <= known
        assert auth["scopes"]["optional"] == []
        assert row["capabilities"] == {"test_connection": True}
    base = set(types[0]["auth"]["scopes"]["required"])
    assert base == {
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    }
    for row in types[1:]:
        assert base < set(row["auth"]["scopes"]["required"])


def test_the_base_scopes_allow_every_step_but_the_membership_ones_and_third_party_links() -> None:
    base = {
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    }
    outside = sorted(oid for oid, e in generic.registry().items() if not set(e["scopes"]) & base)
    assert outside == [
        "create_third_party_link",
        "delete_third_party_link",
        "get_channel_members",
        "get_membership_levels",
        "get_third_party_links",
        "update_third_party_link",
    ]
    monetized = next(
        t
        for t in load("contracts/connection_types.yaml")["connection_types"]
        if t["connection_type_id"] == "youtube_channel_monetized"
    )
    required = set(monetized["auth"]["scopes"]["required"])
    for oid in ("get_channel_members", "get_membership_levels"):
        assert set(generic.registry()[oid]["scopes"]) & required


def test_every_step_names_its_scopes_and_its_quota_cost() -> None:
    quota = build_contracts.quota()["costs"]
    for oid, entry in generic.registry().items():
        for scope in entry["scopes"]:
            assert build_contracts.short_scope(scope) in entry["description"], oid
        if entry["api"] != "data":
            continue
        key = ".".join(entry["vendor_method_id"].split(".")[1:])
        if key in quota:
            assert entry["quota"] == quota[key], oid
            assert quota[key] in entry["description"], oid
        else:
            assert "gives no cost" in entry["description"] or entry["quota"], oid


def test_quota_costs_known_from_the_source_are_used() -> None:
    registry = generic.registry()
    by_method = {e["vendor_method_id"]: e for e in registry.values()}
    assert (
        by_method["youtube.search.list"]["quota"] == "100 quota per day. Each call costs 1 quota."
    )
    assert by_method["youtube.videos.update"]["quota"] == "50"
    assert by_method["youtube.captions.insert"]["quota"] == "400"
    # Not in the quota table, but in the method's own description.
    assert by_method["youtube.liveChatMessages.transition"]["quota"] == "20"
    missing = sorted(
        e["vendor_method_id"]
        for e in registry.values()
        if e["api"] == "data" and e["quota"] is None
    )
    assert missing == [
        "youtube.abuseReports.insert",
        "youtube.captions.download",
        "youtube.comments.markAsSpam",
        "youtube.playlistImages.delete",
        "youtube.playlistImages.insert",
        "youtube.playlistImages.list",
        "youtube.playlistImages.update",
        "youtube.thirdPartyLinks.delete",
        "youtube.thirdPartyLinks.insert",
        "youtube.thirdPartyLinks.list",
        "youtube.thirdPartyLinks.update",
        "youtube.videoTrainability.get",
        "youtube.videos.batchGetStats",
    ]


def test_uploads_follow_the_source_and_the_host_cap() -> None:
    registry = generic.registry()
    uploads = {
        e["vendor_method_id"]: e["body"]["upload"]
        for e in registry.values()
        if e["body"] and e["body"]["upload"]
    }
    methods = source_methods()
    assert set(uploads) == {k for k, m in methods.items() if m.get("supportsMediaUpload")}
    for method_id, media in uploads.items():
        source = methods[method_id]["mediaUpload"]
        assert media["accept"] == source["accept"]
        assert media["source_max_bytes"] == int(source["maxSize"])
        assert media["max_bytes"] == min(int(source["maxSize"]), files.HOST_ARTIFACT_MAX_BYTES)
        assert media["path"] == source["protocols"]["simple"]["path"]
        assert "resumable" in source["protocols"]
    assert uploads["youtube.videos.insert"]["source_max_bytes"] == 274877906944
    assert uploads["youtube.videos.insert"]["max_bytes"] == 200 * 1024 * 1024
    policies = {
        p["operation_id"]: p for p in load("contracts/artifact_policies.yaml")["artifact_policies"]
    }
    video = policies["upload_video_file"]["inputs"][0]
    assert video["max_size_bytes"] == 209715200
    assert video["max_size_env"] == "FS_EXTENSION_ARTIFACT_MAX_BYTES"
    assert (
        policies["upload_video"]["inputs"][0]["max_size_env"] == "FS_EXTENSION_ARTIFACT_MAX_BYTES"
    )
    banner = policies["upload_channel_banner"]["inputs"][0]
    assert banner["max_size_bytes"] == 6291456 and "max_size_env" not in banner
    assert upload.CHUNK_BYTES % (256 * 1024) == 0


def test_downloads_are_declared() -> None:
    policies = {
        p["operation_id"]: p for p in load("contracts/artifact_policies.yaml")["artifact_policies"]
    }
    for oid in catalog.FILE_OUTPUT_IDS:
        assert policies[oid]["outputs"][0]["binding_key"] == files.DOWNLOAD_BINDING
    assert catalog.FILE_OUTPUT_IDS == {
        "download_caption_track",
        "list_channel_videos",
        "list_video_comments",
    }


def test_the_uploaded_video_is_accepted_and_names_its_check_step() -> None:
    registry = generic.registry()
    accepted = {
        oid for oid, e in registry.items() if (e.get("processing") or {}).get("accepted_always")
    }
    assert accepted == {"upload_video_file"}
    assert registry["upload_video_file"]["processing"]["check"] == "get_video_processing_status"
    assert "get_video_processing_status" in catalog.OPERATION_IDS


def _pages() -> list[tuple[str, str]]:
    manifest = load("ui/ui_manifest.yaml")
    out = []
    for ref in manifest["pages"]:
        page = load("ui/" + ref["ref"])
        for comp in page.get("components", []):
            out.append((page["page_id"], str(comp.get("body") or comp.get("content") or "")))
    return out


def test_every_page_is_in_the_manifest() -> None:
    refs = {r["ref"] for r in load("ui/ui_manifest.yaml")["pages"]}
    on_disk = {f"pages/{p.name}" for p in (BUNDLE / "ui" / "pages").glob("*.yaml")}
    assert refs == on_disk


def test_ui_pages_have_no_tables_and_no_forbidden_words() -> None:
    for page_id, body in _pages():
        for line in body.splitlines():
            assert not line.strip().startswith("|"), (page_id, line)
        lowered = body.lower()
        for word in ("not verified", "unverified", "не проверено", "todo", "tbd"):
            assert word not in lowered, (page_id, word)


def test_the_icon_is_a_128_png_and_branding_records_its_source() -> None:
    data = (BUNDLE / "icon.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (128, 128)
    branding = (BUNDLE / "BRANDING.md").read_text(encoding="utf-8")
    assert hashlib.sha256(data).hexdigest() in branding
    assert "youtube-icon.zip" in branding
    assert "ca9b5104387e0f7afcfda3a79c910449561112f1077177dd0d64f8c72f56e476" in branding


def test_version_step_limit_and_changelog() -> None:
    manifest = load("extension.yaml")
    assert manifest["version"] == "0.1.0" == build_contracts.VERSION
    assert manifest["entrypoint"]["timeout_seconds"] == 600
    assert limits.STEP_TIMEOUT_SECONDS == 600
    changelog = (BUNDLE / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.splitlines()[2].startswith("## 0.1.0")
    assert "0.1.0" in json.dumps(load("ui/pages/changelog.yaml"))


def test_vendor_listing_and_repository() -> None:
    manifest = load("extension.yaml")
    assert manifest["extension_id"] == "flowsteward.youtube"
    assert BUNDLE.name == "flowsteward_youtube"
    assert manifest["vendor"] == {
        "name": "Flow Steward",
        "support_url": REPOSITORY + "/issues",
        "website_url": REPOSITORY,
    }
    assert manifest["listing"]["categories"] == ["media", "marketing"]
    assert manifest["listing"]["category"] == "media"
    support = json.dumps(load("ui/pages/support.yaml"))
    assert REPOSITORY in support
    readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    assert REPOSITORY in readme


def test_the_runtime_names_no_server_beyond_youtube() -> None:
    hosts = set()
    for path in (BUNDLE / "runtime").glob("*.py"):
        hosts |= set(re.findall(r"https://([a-z0-9.-]+)", path.read_text(encoding="utf-8")))
    assert hosts <= {
        "youtube.googleapis.com",
        "youtubeanalytics.googleapis.com",
        "developers.google.com",
    }
    egress = set(load("extension.yaml")["egress"]["hosts"])
    assert egress == {"youtube.googleapis.com", "youtubeanalytics.googleapis.com"}
    for api, facts in build_contracts.sources_facts().items():
        assert facts["root_url"].removeprefix("https://").rstrip("/") in egress, api


def test_composite_writes_and_validators_are_declared() -> None:
    assert set(composites.VALIDATORS) == composites.COMPOSITE_WRITES == set(composites.NEUTRAL)
    assert composites.COMPOSITE_WRITES == {
        s["operation_id"] for s in composite_specs.COMPOSITES if s["kind"] == "write"
    }


def test_readme_follows_the_structure() -> None:
    readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# YouTube integration for Flow Steward\n")
    headings = re.findall(r"^## (.+)$", readme, re.MULTILINE)
    assert headings == [
        "What is this",
        "What you can automate",
        "Why teams use it",
        "What's inside",
        "Get started",
        "Requirements",
        "FAQ",
        "In your language",
        "Links",
        "For developers",
    ]
    assert '<img src="icon.png"' in readme and "img.shields.io" in readme
    assert readme.rstrip().splitlines()[-1].startswith("YouTube and the YouTube logo")
