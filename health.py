"""Health command for the YouTube extension (no network)."""

from __future__ import annotations

import json


def check_health() -> dict[str, object]:
    from runtime.catalog import OPERATION_IDS, WRITE_OPERATION_IDS
    from runtime.generic import REGISTRY_FILE

    sources = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["sources"]
    return {
        "extension_id": "flowsteward.youtube",
        "ok": True,
        "status": "healthy",
        "specification_sha256": {name: s["sha256"] for name, s in sources.items()},
        "specification_version": {name: s["revision"] for name, s in sources.items()},
        "declared_operations": len(OPERATION_IDS),
        "effect_operations": len(WRITE_OPERATION_IDS),
    }


if __name__ == "__main__":
    print(json.dumps(check_health(), separators=(",", ":"), sort_keys=True))
