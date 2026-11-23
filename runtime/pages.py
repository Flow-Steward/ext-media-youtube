"""Lists read page after page with YouTube's page tokens.

A list method of the pinned documents takes ``pageToken`` and answers ``items`` and,
while more follow, ``nextPageToken``. Reading all pages follows ``nextPageToken`` until
YouTube sends none, the asked maximum is reached, the step output (or the workflow file)
is full or the time left is too short; then it returns what it read with ``complete``
false and ``next_page_token``, the token of the first page not returned. A read never
fails because of that.

The continuation is exact: a page is returned whole or not at all, so the next step
started with ``next_page_token`` reads exactly the records not returned. A token is
always sent with the page size it was issued for: the page size is changed only for the
first page of a list (no token sent yet), which is asked again with half the records
when it does not fit; the rest of the list then keeps that smaller size. A page token
YouTube sends twice, or an empty page while the list is not finished, never ends the
list as complete.

The whole result is measured, not only the records: its envelope (with the widest
values the step can put there), the warnings so far, the pending ones and room for the
closing warning, plus each record as it is added. So the final budget check never
refuses what was taken here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import budget, errors, files
from .context import Context
from .errors import ExtensionError
from .transport import MIN_CALL_WINDOW_SECONDS, DeadlineReached, TooDeep, dumps_json

#: The longest warning a list step adds when it stops; the budget keeps room for it.
MAX_STOP_WARNING = 600
_STOP_RESERVE = "x" * MAX_STOP_WARNING
#: The longest page token kept for the continuation.
MAX_TOKEN = 1000
FILE_CONTENT_TYPE = "application/json"
MAX_FILE_BYTES = files.MAX_DOWNLOAD_BYTES - 1024


class Pages:
    """Collects the records of a paged read into the step output or a workflow file."""

    def __init__(self, to_file: bool, key: str, envelope: dict[str, Any]) -> None:
        self.to_file = to_file
        self.key = key
        self.envelope = envelope
        self.items: list[Any] = []
        self.size = 2
        self.records = budget.Totals()
        self.warnings: list[str] = []
        self.complete = False

    def take(self, page: list[Any], pending: list[str]) -> bool:
        """Add a page and its pending warnings; False (nothing added) when they do not fit."""
        if self.to_file:
            size = self.size + sum(len(dumps_json(item).encode("utf-8")) + 1 for item in page)
            if size > MAX_FILE_BYTES:
                return False
            frame = budget.measure(
                {**self.envelope, "warnings": [*self.warnings, *pending, _STOP_RESERVE]}
            )
            if not frame.within():
                return False
            self.size = size
        else:
            added = self.records
            for item in page:
                cost = budget.measure(item)
                # One level for the list, one for the result object.
                added = added + budget.Totals(cost.nodes, cost.depth + 2, cost.size + 1)
            frame = budget.measure(
                {
                    **self.envelope,
                    self.key: [],
                    "warnings": [*self.warnings, *pending, _STOP_RESERVE],
                }
            )
            if not (added + frame).within():
                return False
            self.records = added
        self.items += page
        self.warnings += pending
        return True


def stop_warning(text: str) -> str:
    return errors.safe_text(text, MAX_STOP_WARNING)


def transient(exc: ExtensionError) -> bool:
    """Read failures after which the pages already read are returned (HTTP 429, 408 and
    5xx, network failures and time-outs of a read): the read can be continued later."""
    return exc.retryable is True


def too_large_answer(exc: ExtensionError) -> bool:
    """YouTube's answer was larger than the transport reads (a read: nothing changed)."""
    return exc.code == errors.RESPONSE_TOO_LARGE and exc.definitely_no_external_effect is True


def room(context: Context) -> bool:
    """Whether another page can still be started and read in time."""
    return context.transport.remaining() >= MIN_CALL_WINDOW_SECONDS + 15


def out_of_time(context: Context) -> ExtensionError:
    """No page fitted before the time ran out, after requests were already made."""
    return errors.no_effect(
        errors.TIMEOUT,
        f"The step ran out of time after {context.transport.calls} requests to YouTube while "
        "asking for a page small enough to return; nothing was changed. Run it again with "
        "narrower filters",
    )


def bad(shown: str, what: str) -> ExtensionError:
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        f"YouTube's answer to {shown} {what}",
        failure_class="provider",
        retryable=False,
    )


def split(data: Any, shown: str) -> tuple[list[Any], str | None, dict[str, Any]]:
    """A page's ``items``, its ``nextPageToken`` and the rest of the answer."""
    if not isinstance(data, Mapping):
        raise bad(shown, "is not a JSON object")
    items = data.get("items", [])
    if not isinstance(items, list):
        raise bad(shown, "has an items value that is not a list")
    token = data.get("nextPageToken")
    if token is not None and (not isinstance(token, str) or not token.strip()):
        raise bad(shown, "has a nextPageToken that is not text")
    if isinstance(token, str) and len(token) > MAX_TOKEN:
        raise bad(shown, f"has a nextPageToken longer than {MAX_TOKEN} characters")
    rest = {k: v for k, v in data.items() if k not in {"items", "nextPageToken", "prevPageToken"}}
    return items, token, rest


def one_page(data: Any, shown: str) -> dict[str, Any]:
    """The outputs of a list step that reads one page."""
    items, token, rest = split(data, shown)
    return {
        "data": rest,
        "items": items,
        "count": len(items),
        "complete": token is None,
        "next_page_token": token,
    }


def _key(item: Any) -> str | None:
    """What identifies a record for removing duplicates: its ``id`` (text or object)."""
    if isinstance(item, Mapping) and "id" in item:
        return dumps_json(item["id"])
    return None


def read_all(context: Context, operation_id: str, plan: Any) -> dict[str, Any]:
    """A generated list step with ``all_pages``."""
    from . import generic

    entry = generic.spec(operation_id)
    pager = entry["pager"]
    query = [(k, v) for k, v in plan.query if k not in {pager["token"], pager["size"]}]
    start = next((v for k, v in plan.query if k == pager["token"]), None)
    sized = pager["size"] is not None
    size = next((int(v) for k, v in plan.query if k == pager["size"]), pager["max"] or 1)

    last: dict[str, Any] = {}

    def fetch(token: str | None, limit: int) -> Any:
        page_query = list(query)
        if token is not None:
            page_query.append((pager["token"], token))
        if sized:
            page_query.append((pager["size"], str(limit)))
        call = generic.to_call(entry, _with_query(plan, page_query))
        answer = context.transport.read(call)
        last["status"] = answer.status
        return generic._read_json(context, answer, plan.shown)

    result = collect(
        context,
        fetch=fetch,
        shown=plan.shown,
        start=start,
        page_size=size,
        smallest=pager["min"],
        most=plan.max_items,
        to_file=False,
        out_key="items",
    )
    return {"status": last.get("status"), **result, "etag": None}


def _with_query(plan: Any, query: list[tuple[str, str]]) -> Any:
    from dataclasses import replace

    return replace(plan, query=query)


def collect(
    context: Context,
    *,
    fetch: Any,
    shown: str,
    start: str | None,
    page_size: int,
    smallest: int,
    most: int,
    to_file: bool,
    out_key: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pages read by token until the list ends; see the module text."""
    envelope: dict[str, Any] = {
        **(extra or {}),
        "count": 10**9,
        "complete": False,
        "next_page_token": "x" * MAX_TOKEN,
        "file": "x" * 100,
        "data": None,
    }
    pages = Pages(to_file, out_key, envelope)
    token = start
    seen_tokens: set[str] = set()
    seen: set[str] = set()
    first = True
    stopped = ""
    size = max(smallest, page_size)
    meta: dict[str, Any] | None = None
    while True:
        left = most - len(pages.items)
        if left <= 0:
            stopped = f"the {most} asked for were read"
            break
        if left < smallest:
            stopped = f"fewer than {smallest} of the {most} asked for are left, the smallest page"
            break
        if context.transport.calls and not room(context):
            if first:
                raise out_of_time(context)
            stopped = "time ran out"
            break
        limit = max(smallest, min(size, left))
        try:
            data = fetch(token, limit)
        except DeadlineReached:
            if first and context.transport.calls:
                raise out_of_time(context) from None
            if first:
                raise
            stopped = "time ran out"
            break
        except ExtensionError as exc:
            if too_large_answer(exc) and token is None and limit > smallest:
                size = max(smallest, limit // 2)
                continue
            if first or not (transient(exc) or too_large_answer(exc)):
                raise
            stopped = f"YouTube could not give the next page ({exc.code}: {exc.message})"
            break
        except TooDeep:  # pragma: no cover - _read_json turns it into an error
            raise bad(shown, "is nested too deeply") from None
        page, following, rest = split(data, shown)
        fresh = []
        for item in page:
            key = _key(item)
            if key is not None and key in seen:
                continue
            fresh.append(item)
        pending = []
        if len(fresh) != len(page):
            pending.append(
                f"{len(page) - len(fresh)} records appeared twice because the list changed while "
                "it was read; each is returned once"
            )
        if meta is None:
            pages.envelope["data"] = rest
        if not pages.take(fresh, pending):
            if token is None and limit > smallest:
                # The first page does not fit: ask again for half as many records.
                size = max(smallest, limit // 2)
                continue
            if first:
                raise budget.too_large()
            stopped = "the output is full" if not to_file else "the file is full"
            break
        if meta is None:
            meta = rest
        seen.update(k for k in map(_key, fresh) if k is not None)
        first = False
        if following is None:
            pages.complete = True
            break
        if following in seen_tokens or following == token:
            raise bad(shown, "sent the same page token twice; the read is not complete")
        seen_tokens.add(following)
        token = following
    if not pages.complete:
        pages.warnings.append(
            stop_warning(
                f"Stopped early because {stopped}; run the step again with page_token "
                f"{token} for the rest"
                if token is not None
                else f"Stopped early because {stopped}; run the step again for the rest"
            )
        )
    result: dict[str, Any] = {**(extra or {}), "count": len(pages.items)}
    if pages.to_file:
        handle = None
        if pages.items:
            handle = files.save(
                context,
                dumps_json(pages.items).encode("utf-8"),
                content_type=FILE_CONTENT_TYPE,
                what="The list",
            )
        result[out_key] = []
        result["file"] = handle
    else:
        result[out_key] = pages.items
    result["complete"] = pages.complete
    result["next_page_token"] = None if pages.complete else token
    if not to_file and out_key == "items":
        result["data"] = meta
    result["warnings"] = pages.warnings
    return result


__all__ = [
    "Pages",
    "bad",
    "collect",
    "one_page",
    "read_all",
    "room",
    "split",
    "stop_warning",
    "too_large_answer",
    "transient",
]
