"""Runners of the generated steps: one method of the pinned Discovery document each.

What each step accepts and how its answer is read comes from runtime/registry.json,
built from the pinned document by tests/reference/build_contracts.py:

- the path parameter is required text, percent-encoded as one path segment;
- query parameters are typed by the document (text, whole number with its minimum and
  maximum, true/false, RFC 3339 date-time, allowed values); a
  ``repeated`` one takes a list and sends one parameter per value;
- a request body (the method's ``request`` schema) is the ``body`` input, sent as given
  with exact decimals; a field the schema does not list is refused before sending,
  because Google refuses unknown fields;
- a method that supports media upload takes a workflow file (``file``) and sends it with
  YouTube's resumable upload protocol (runtime/upload.py), the metadata in ``body``;
- a method that supports media download saves the file YouTube sends as a workflow file
  (``alt=media``, as the Google API client asks for media);
- a list method (``pageToken`` in, ``nextPageToken`` and ``items`` out) returns ``items``,
  ``count``, ``complete`` and ``next_page_token``; with ``all_pages`` it reads page after
  page (runtime/pages.py);
- a JSON answer is ``data``; one nested deeper than 48 levels is not read (a read fails
  with ``invalid_response``, a confirmed write returns its facts with ``data`` empty and
  a warning);
- a write returns ``processing``: ``completed`` when YouTube answered that the change is
  made, ``accepted`` for an uploaded video, which YouTube processes afterwards; then
  ``applied`` is false and ``check`` names the step that reads the processing status.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import budget, errors, files, nesting, outcome, pages, upload
from .context import Context
from .errors import invalid
from .params import check, integer, wire
from .transport import (
    MAX_ANSWER_BYTES,
    MAX_FILE_ANSWER_BYTES,
    Answer,
    Call,
    TooDeep,
    dumps_json,
)

REGISTRY_FILE = Path(__file__).resolve().parent / "registry.json"
#: Inputs a paged step adds.
PAGE_INPUTS = frozenset({"all_pages", "max_items"})
#: The most records ``all_pages`` reads in one step.
MAX_ITEMS = 100_000
DEFAULT_ITEMS = 10_000


@cache
def _data() -> dict[str, Any]:
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def registry() -> dict[str, dict[str, Any]]:
    return dict(_data()["operations"])


def spec(operation_id: str) -> dict[str, Any]:
    return _data()["operations"][operation_id]


def inputs_of(entry: Mapping[str, Any]) -> set[str]:
    names = {p["input"] for p in entry["path_params"] + entry["query"]}
    body = entry["body"]
    if body:
        if body["json"]:
            names.add("body")
        if body["upload"]:
            names |= {"file", "content_type"}
    if entry["pager"]:
        names |= PAGE_INPUTS
    return names


@dataclass
class Plan:
    """A checked request; the file it uploads is read only when it is sent."""

    method: str
    path: str
    api: str
    shown: str
    query: list[tuple[str, str]] = field(default_factory=list)
    body: bytes | None = None
    content_type: str | None = None
    file_handle: str | None = None
    #: The media type the uploaded file is sent as.
    file_type: str | None = None
    #: True when the answer is saved as a workflow file.
    as_file: bool = False
    all_pages: bool = False
    max_items: int = DEFAULT_ITEMS


def media_allowed(accepted: list[str], chosen: str) -> bool:
    """Whether ``chosen`` matches one of the document's ``accept`` patterns (``video/*``)."""
    for pattern in accepted:
        if pattern == "*/*" or pattern == chosen:
            return True
        if (
            pattern.endswith("/*")
            and chosen.startswith(pattern[:-1])
            and len(chosen) > len(pattern[:-1])
        ):
            return True
    return False


def _media_type(value: Any) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    if (
        not text
        or len(text) > 100
        or text.count("/") != 1
        or any(not (ch.isalnum() or ch in "/.+-_") for ch in text)
    ):
        raise invalid("content_type must be a media type such as video/mp4 or image/png")
    return text


def prepare(operation_id: str, operation_input: Mapping[str, Any]) -> Plan:
    """The checked request of a generated step (also its test-run check)."""
    entry = spec(operation_id)
    given = {k: v for k, v in operation_input.items() if k != "connection_ref"}
    unknown = sorted(set(given) - inputs_of(entry))
    if unknown:
        raise invalid(f"The step input has unknown fields: {', '.join(unknown[:10])}")
    path = entry["path"]
    for prm in entry["path_params"]:
        value = given.get(prm["input"])
        if value is None or value == "":
            raise invalid(f"{prm['input']} is required")
        segment = check(prm["node"], value, prm["input"])
        path = path.replace("{" + prm["name"] + "}", quote(str(segment), safe=""))
    plan = Plan(
        method=entry["method"],
        path=path,
        api=entry["api"],
        shown=f"{entry['method']} {entry['path']}",
    )
    for prm in entry["query"]:
        value = given.get(prm["input"])
        if value is None or value == "" or value == []:
            if prm["node"]["required"]:
                raise invalid(f"{prm['input']} is required")
            continue
        checked = check(prm["node"], value, prm["input"])
        if isinstance(checked, list):
            plan.query += [(prm["name"], wire(item)) for item in checked]
        else:
            plan.query.append((prm["name"], wire(checked)))
    if entry["answer"] == "file":
        plan.as_file = True
        plan.query.append(("alt", "media"))
    if entry["pager"]:
        flag = given.get("all_pages", False)
        if not isinstance(flag, bool):
            raise invalid("all_pages must be true or false")
        plan.all_pages = flag
        if "max_items" in given:
            if not flag:
                raise invalid("max_items applies only with all_pages")
            plan.max_items = integer(
                {"minimum": 1, "maximum": MAX_ITEMS}, given["max_items"], "max_items"
            )
    _body(entry, given, plan)
    return plan


def _body(entry: Mapping[str, Any], given: Mapping[str, Any], plan: Plan) -> None:
    body = entry["body"]
    if not body:
        return
    shape = body["json"]
    has_json = given.get("body") not in (None, "", {}, [])
    has_file = given.get("file") not in (None, "")
    if "content_type" in given and not has_file:
        raise invalid("content_type applies only with file")
    if has_json and shape:
        value = given["body"]
        if not isinstance(value, Mapping):
            raise invalid("body must be a JSON object")
        extra = sorted(str(k) for k in value if k not in shape["properties"])
        if extra:
            raise invalid(
                f"body has fields the {shape['schema']} resource does not have: "
                + ", ".join(extra[:10])
            )
        plan.body = dumps_json(value).encode("utf-8")
        plan.content_type = "application/json"
    elif shape and body["required"]:
        raise invalid(f"body is required: the {shape['schema']} resource as JSON")
    media = body["upload"]
    if has_file and media:
        handle = given["file"]
        if not isinstance(handle, str) or not handle.strip():
            raise invalid("file must be a workflow file from an earlier step")
        plan.file_handle = handle.strip()
        chosen = (
            _media_type(given["content_type"]) if "content_type" in given else media["default_type"]
        )
        if not media_allowed(media["accept"], chosen):
            raise invalid("content_type must match one of: " + ", ".join(media["accept"]))
        plan.file_type = chosen
    elif media and media["required"]:
        raise invalid("file is required: the workflow file to upload")


def to_call(entry: Mapping[str, Any], plan: Plan) -> Call:
    return Call(
        method=plan.method,
        path=plan.path,
        shown=plan.shown,
        api=plan.api,
        query=tuple(plan.query),
        body=plan.body,
        content_type=plan.content_type,
        limit=MAX_FILE_ANSWER_BYTES if plan.as_file else MAX_ANSWER_BYTES,
    )


def _read_json(context: Context, answer: Answer, shown: str) -> Any:
    """A read's JSON value; an empty or invalid answer is an error (nothing changed)."""
    if answer.empty:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"YouTube answered {shown} without a body",
            failure_class="provider",
            retryable=False,
        )
    try:
        return context.transport.json(answer)
    except ValueError as exc:
        what = (
            f"JSON nested deeper than {nesting.MAX_ANSWER_DEPTH} levels; it is not read"
            if isinstance(exc, TooDeep)
            else "something that is not JSON"
        )
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"YouTube answered {shown} with {what}",
            failure_class="provider",
            retryable=False,
        ) from None


def read_result(
    context: Context, entry: Mapping[str, Any], answer: Answer, plan: Plan
) -> dict[str, Any]:
    """The outputs of a read YouTube answered with a success status."""
    result: dict[str, Any] = {"status": answer.status}
    warnings: list[str] = []
    if plan.as_file:
        handle = None
        if not answer.empty:
            # A caption track is text: the token is removed like from any answer.
            content = context.transport.scrub_bytes(answer.raw)
            handle = files.save(
                context, content, content_type=entry["file"]["content_type"], what="The file"
            )
        else:
            warnings.append(f"YouTube answered {plan.shown} (HTTP {answer.status}) without a file")
        result.update(
            file=handle,
            content_type=answer.content_type or None,
            size_bytes=len(answer.raw) if handle else None,
        )
    else:
        data = _read_json(context, answer, plan.shown)
        if entry["pager"]:
            result.update(pages.one_page(data, plan.shown))
        else:
            result["data"] = data
    result["etag"] = answer.headers.get("ETag")
    result["warnings"] = warnings
    return result


def write_result(
    context: Context, entry: Mapping[str, Any], answer: Answer, plan: Plan
) -> dict[str, Any]:
    """The outputs of a write YouTube answered with a success status (table T)."""
    out = outcome.write_outcome(
        context,
        answer,
        plan.shown,
        entry=entry,
        promised=entry["answer"] == "json",
    )
    result: dict[str, Any] = {"status": answer.status, **out}
    result["etag"] = answer.headers.get("ETag")
    result["warnings"] = out["warnings"]
    return result


def run(context: Context, operation_id: str) -> dict[str, Any]:
    entry = spec(operation_id)
    plan = prepare(operation_id, context.operation_input)
    if entry["kind"] == "read":
        if plan.all_pages:
            return pages.read_all(context, operation_id, plan)
        answer = context.transport.read(to_call(entry, plan))
        result = read_result(context, entry, answer, plan)
        budget.ensure_fits(result)
        return result
    if plan.file_handle is not None:
        media = entry["body"]["upload"]
        content = files.read(context, plan.file_handle, max_bytes=media["max_bytes"])
        answer = upload.resumable(
            context,
            method=plan.method,
            upload_path=media["path"],
            api=plan.api,
            shown=plan.shown,
            query=plan.query,
            metadata=plan.body,
            content=content,
            content_type=plan.file_type or "application/octet-stream",
        )
    else:
        answer = context.transport.write(to_call(entry, plan))
    return write_result(context, entry, answer, plan)


__all__ = [
    "Plan",
    "inputs_of",
    "media_allowed",
    "prepare",
    "read_result",
    "registry",
    "run",
    "spec",
    "to_call",
    "write_result",
]
