"""The pages a user reads in Flow Steward and the README: present, complete, factual."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PAGES = {"setup-guide", "connection", "api-coverage", "changelog", "support"}
#: Words that describe the extension as unfinished; vendor rules are stated as facts.
FORBIDDEN = (
    "outside this version",
    "not in this version",
    "not part of this version",
    "not in this release",
    "not included in this release",
    "not yet",
    "limitation",
    "pilot",
)


def _pages() -> dict[str, dict]:
    refs = yaml.safe_load((ROOT / "ui/ui_manifest.yaml").read_text())["pages"]
    return {ref["ref"]: yaml.safe_load((ROOT / "ui" / ref["ref"]).read_text()) for ref in refs}


def test_the_pages_a_user_needs_are_registered():
    ids = [page["page_id"] for page in _pages().values()]
    assert len(ids) == len(set(ids))
    assert REQUIRED_PAGES <= set(ids)


def test_every_connection_type_has_a_project_scoped_page_with_its_form():
    types = {
        row["connection_type_id"]
        for row in yaml.safe_load((ROOT / "contracts/connection_types.yaml").read_text())[
            "connection_types"
        ]
    }
    found = set()
    for page in _pages().values():
        forms = [c for c in page["components"] if c["type"] == "connection_form"]
        if forms:
            assert page.get("project_scoped") is True, page["page_id"]
            found |= {c["data"]["connection_type"] for c in forms}
    assert found == types


def test_no_markdown_table_and_no_unfinished_wording():
    texts = [(ROOT / "README.md").read_text()]
    for page in _pages().values():
        for component in page["components"]:
            body = component.get("body", "")
            assert not any(line.lstrip().startswith("|") for line in body.splitlines())
            texts.append(body)
    texts.append(yaml.safe_load((ROOT / "extension.yaml").read_text())["description"])
    for text in texts:
        for word in FORBIDDEN:
            assert word not in text.lower(), word


def test_the_listing_describes_the_extension_in_full():
    description = yaml.safe_load((ROOT / "extension.yaml").read_text())["description"]
    assert len(description) >= 500
