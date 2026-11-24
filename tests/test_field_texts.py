"""Every input reads clearly, and the same input reads the same in every step."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "reference"))

import field_texts  # noqa: E402


def _forms() -> list[dict]:
    return yaml.safe_load((ROOT / "contracts/step_ui_manifest.yaml").read_text())["forms"]


def test_every_input_has_a_label_and_a_description():
    for form in _forms():
        for field in form["fields"]:
            label, text = field.get("label", ""), field.get("help_text", "")
            assert label and text, (form["operation_id"], field["name"])
            assert not re.search(r"[a-z][A-Z]", label), (form["operation_id"], label)
            assert text.strip().lower() != field["name"].lower(), (form["operation_id"], text)


def test_an_input_has_one_label_in_every_step():
    labels: dict[str, set[str]] = defaultdict(set)
    for form in _forms():
        for field in form["fields"]:
            labels[field["name"]].add(field["label"])
    assert {name: found for name, found in labels.items() if len(found) > 1} == {}


def test_an_input_that_means_the_same_is_described_the_same():
    texts: dict[str, set[str]] = defaultdict(set)
    for form in _forms():
        for field in form["fields"]:
            texts[field["name"]].add(field["help_text"])
    for name, expected in field_texts.SAME.items():
        if name in texts:
            assert texts[name] == {expected[:400]}, name
