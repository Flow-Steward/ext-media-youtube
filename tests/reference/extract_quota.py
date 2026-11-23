#!/usr/bin/env python3
"""Extract the quota cost table of the YouTube Data API from its pinned documentation page.

Source: https://developers.google.com/youtube/data/determine_quota_cost?hl=en
(https://developers.google.com/youtube/v3/determine_quota_cost answers 301 to it),
downloaded 2026-11-23 into tests/reference/sources/determine_quota_cost.html. The page
itself is not committed (it carries the site's own scripts); its SHA-256 is pinned here
and the extracted table is committed as quota_costs.json. Run from the bundle root:

    python3 -I tests/reference/extract_quota.py

A page with another SHA-256 is refused: the pinned facts change only on purpose.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sources" / "determine_quota_cost.html"
OUTPUT = HERE / "quota_costs.json"
URL = "https://developers.google.com/youtube/data/determine_quota_cost?hl=en"
SHA256 = "d56a9e93a260e2d351fa40a883d7c105ee228f051e6d391070bd39ba0bd0d99f"
BYTES = 142880
DOWNLOADED = "2026-11-23"

_ROW = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_UPDATED = re.compile(r"Last updated (\d{4}-\d{2}-\d{2}) UTC")


def _text(cell: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", cell)).split())


def extract(raw: bytes) -> dict[str, object]:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"the documentation page changed (SHA-256 {digest}); pin it again")
    page = raw.decode("utf-8")
    start = page.index("<table")
    table = page[start : page.index("</table>", start)]
    costs: dict[str, str] = {}
    resource = ""
    for row in _ROW.findall(table):
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) != 3 or cells[0] == "resource":
            continue
        if cells[0]:
            resource = cells[0]
        if not resource or not cells[1] or not cells[2]:
            raise SystemExit(f"a quota row is incomplete: {cells}")
        costs[f"{resource}.{cells[1]}"] = cells[2]
    updated = _UPDATED.search(page)
    return {
        "source": {
            "url": URL,
            "sha256": SHA256,
            "bytes": BYTES,
            "downloaded": DOWNLOADED,
            "last_updated": updated.group(1) if updated else None,
        },
        "costs": costs,
    }


def main() -> int:
    facts = extract(SOURCE.read_bytes())
    OUTPUT.write_text(json.dumps(facts, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("quota costs:", len(facts["costs"]))  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
