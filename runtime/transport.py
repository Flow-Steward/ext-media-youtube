"""The only way this extension reaches YouTube.

Each step is one REST call (or, for an upload, the calls of YouTube's resumable upload
protocol) to ``https://youtube.googleapis.com`` (YouTube Data API v3), the ``rootUrl``
of the pinned Discovery document, with the method and path the document gives. The
access token travels only in the ``Authorization: Bearer`` header. Requests go out
through the public Flow Steward extension SDK, which pins DNS, verifies the connected
peer, refuses redirects and enforces the timeout; they are sent one at a time, never in
parallel, and never retried.

The Discovery document gives each method's response schema, not its HTTP statuses, so
any 2xx status is a success. Refusals carry Google's error object
(``{"error": {"code", "message", "errors": [{"reason", "message", ...}], "status"}}``);
only its texts reach the step's error, bounded and with the token removed. The reasons
and statuses are those of the YouTube Data API errors page
(https://developers.google.com/youtube/v3/docs/errors): for example ``quotaExceeded``
(HTTP 403) when the project's daily quota is used up.

Outcome of a write: a refusal shows that nothing changed when its status is 4xx and its
body is Google's error object for that same status, and for HTTP 429. Every other
failure after the request was sent (a 5xx, a 4xx without the error object, a broken
connection, a time-out) leaves the write ``timeout_unknown``, and nothing is retried.
"""

from __future__ import annotations

import http.client
import json
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

from flowsteward_extension_sdk import PinnedPeerError, open_pinned_url, parse_retry_after

from . import errors, nesting, numbers
from .connection import HOSTS, Connection, secret_forms
from .errors import ExtensionError

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_BODY_BYTES = 20 * 1024 * 1024
#: The most read from a JSON answer.
MAX_ANSWER_BYTES = 30 * 1024 * 1024
#: The most read from a file answer (a caption track).
MAX_FILE_ANSWER_BYTES = 40 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
CHUNK_BYTES = 64 * 1024
#: Shortest window still worth starting a request in.
MIN_CALL_WINDOW_SECONDS = 15.0
_USER_AGENT = "FlowSteward-YouTube/0.1"
_PATH_RE = re.compile(r"^(/[A-Za-z0-9%._~:-]+)+$")
CHECK = "; check in YouTube what changed before running the step again"
#: Response headers a step may return or the upload reads.
KEPT_HEADERS = ("Location", "ETag", "Last-Modified", "Retry-After", "Range")
#: Error reasons of HTTP 403 that mean a quota or rate limit, not a missing permission
#: (YouTube Data API errors page).
QUOTA_REASONS = frozenset(
    {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"}
)
#: Any 2xx status is a success (the Discovery document gives no statuses).
ANY_2XX = "2xx"


class DeadlineReached(Exception):
    """The invocation's time budget leaves no room for another request."""


@dataclass
class Answer:
    status: int
    raw: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)
    #: Why the body of a confirmed write was not read (too large, too late); then
    #: ``raw`` is empty and only the status and the headers are known.
    unread: str | None = None

    @property
    def empty(self) -> bool:
        return not self.raw.strip()


@dataclass(frozen=True)
class Call:
    """One request, as the registry describes it."""

    method: str
    path: str
    shown: str
    #: "data": the YouTube Data API (the only API of this extension).
    api: str = "data"
    query: Sequence[tuple[str, str]] = ()
    headers: Mapping[str, str] = field(default_factory=dict)
    accept: str = "application/json"
    body: bytes | None = None
    content_type: str | None = None
    #: Success statuses: ``2xx`` for any, or the exact ones (an upload chunk adds 308).
    success: Sequence[str] = (ANY_2XX,)
    limit: int = MAX_ANSWER_BYTES
    #: An upload session address YouTube returned (instead of ``path`` and ``query``).
    session_url: str | None = None

    def succeeded(self, status: int) -> bool:
        return str(status) in self.success or (ANY_2XX in self.success and 200 <= status < 300)


class YouTubeTransport:
    """Sends YouTube requests for one connection."""

    def __init__(
        self,
        connection: Connection,
        *,
        opener: Callable[..., Any] = open_pinned_url,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._connection = connection
        self._opener = opener
        self.clock = clock
        self._timeout_seconds = timeout_seconds
        self._call_timeout = timeout_seconds
        #: The token's forms, computed once for the connection (scrub runs per value).
        self._forms = connection.secret_forms()
        self._forms_bytes = tuple(form.encode("utf-8") for form in self._forms)
        #: True once a request that can change data may have left this process.
        self.mutated = False
        #: True once YouTube confirmed a change in this invocation.
        self.committed = False
        #: Monotonic time after which no request may start (set by the operation).
        self.deadline: float | None = None
        #: Requests started in this invocation.
        self.calls = 0

    @property
    def connection(self) -> Connection:
        return self._connection

    def remaining(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - self.clock()

    # -- public calls --------------------------------------------------------

    def read(self, call: Call) -> Answer:
        return self._call(call, mutating=False)

    def write(self, call: Call) -> Answer:
        """A change; its answer once YouTube confirmed it."""
        answer = self._call(call, mutating=True)
        self.committed = True
        return answer

    def write_unconfirmed(self, call: Call) -> Answer:
        """The last part of an upload: it may create the resource, but YouTube may also
        answer that bytes are still missing (HTTP 308), so it is not yet confirmed."""
        return self._call(call, mutating=True)

    def prepare_upload(self, call: Call) -> Answer:
        """A request of an upload that cannot change anything by itself: opening the
        upload session, and a part of the file that is not the last (YouTube creates
        nothing before the last byte arrived). Failures are failures of a read."""
        return self._call(call, mutating=False)

    def add_secret(self, secret: str) -> None:
        """Remove ``secret`` (an upload session address) from answers too."""
        forms = set(self._forms) | set(secret_forms(secret))
        self._forms = tuple(sorted(forms, key=len, reverse=True))
        self._forms_bytes = tuple(form.encode("utf-8") for form in self._forms)

    # -- answers -------------------------------------------------------------

    def scrub(self, value: Any) -> Any:
        """The token removed from every text and key of a parsed answer."""
        if isinstance(value, str):
            for form in self._forms:
                if form in value:
                    value = value.replace(form, "[redacted]")
            return value
        if isinstance(value, Mapping):
            return {self.scrub(k): self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def scrub_bytes(self, raw: bytes) -> bytes:
        for encoded in self._forms_bytes:
            if encoded in raw:
                raw = raw.replace(encoded, b"[redacted]")
        return raw

    def json(self, answer: Answer) -> Any:
        """The answer's JSON value (numbers with a point as Decimal), token removed.
        ValueError when it is not JSON."""
        return self.scrub(parse_json(answer.raw))

    def text(self, answer: Answer, limit: int = 100_000) -> str:
        return self.scrub(answer.raw.decode("utf-8", "replace"))[:limit]

    # -- one request ---------------------------------------------------------

    def _call(self, call: Call, *, mutating: bool) -> Answer:
        if not _PATH_RE.fullmatch(call.path) or call.api not in HOSTS:
            raise errors.invalid("Not a YouTube operation")
        headers = {
            "Accept": call.accept,
            "User-Agent": _USER_AGENT,
            "Authorization": "Bearer " + self._connection.access_token,
        }
        for name, value in call.headers.items():
            headers[name] = value
        if call.body is not None:
            if len(call.body) > MAX_REQUEST_BODY_BYTES:
                raise errors.invalid("The request is larger than the 20 MB this extension sends")
            headers["Content-Type"] = call.content_type or "application/json"
        if call.session_url is not None:
            url = _session_url(call.session_url, self._connection.base_url(call.api))
        else:
            url = self._connection.base_url(call.api) + call.path
            if call.query:
                url += "?" + urlencode(list(call.query))
        request = Request(url, method=call.method, data=call.body, headers=headers)
        remaining = self.remaining()
        if remaining < MIN_CALL_WINDOW_SECONDS:
            raise DeadlineReached
        self._call_timeout = min(self._timeout_seconds, remaining)
        self.calls += 1
        if mutating:
            self.mutated = True
        expires = None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS
        progress: dict[str, Any] = {}
        if expires is None:
            return self._exchange(request, call, mutating, progress)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["value"] = self._exchange(request, call, mutating, progress)
            except BaseException as exc:  # handed to the caller below
                outcome["error"] = exc

        worker = threading.Thread(target=work, name="youtube-call", daemon=True)
        worker.start()
        worker.join(max(0.0, expires - self.clock()))
        if worker.is_alive():
            confirmed = progress.get("confirmed")
            if isinstance(confirmed, Answer):
                # The status confirmed the write before its body finished arriving.
                return confirmed
            _late(mutating)
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def _exchange(
        self, request: Request, call: Call, mutating: bool, progress: dict[str, Any]
    ) -> Answer:
        expires = None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS
        try:
            with self._opener(
                request, timeout_seconds=self._call_timeout, purpose="YouTube"
            ) as response:
                status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
                headers = getattr(response, "headers", None) or {}
                confirmed: Answer | None = None
                if mutating and 200 <= status < 300 and call.succeeded(status):
                    # The status is known before the body: a documented success confirms
                    # the write whatever happens to the body afterwards.
                    confirmed = Answer(
                        status,
                        b"",
                        _media(headers),
                        _kept_headers(headers, self.scrub),
                        unread="did not arrive in time",
                    )
                    progress["confirmed"] = confirmed
                try:
                    raw = read_bounded(
                        response,
                        call.limit,
                        mutating=mutating,
                        expires=expires,
                        clock=self.clock,
                        per_read=self._call_timeout,
                    )
                except ExtensionError as exc:
                    if confirmed is None:
                        raise
                    confirmed.unread = (
                        f"is larger than the {call.limit // (1024 * 1024)} MB this extension reads"
                        if exc.code == errors.RESPONSE_TOO_LARGE
                        else "did not arrive in time"
                    )
                    return confirmed
                except (OSError, http.client.HTTPException):
                    if confirmed is None:
                        raise
                    confirmed.unread = "was cut off by the connection"
                    return confirmed
        except HTTPError as exc:
            try:
                body = exc.read(MAX_ERROR_BODY_BYTES)
            except Exception:  # pragma: no cover - upstream body is optional
                body = b""
            status = int(exc.code)
            kept = _kept_headers(exc.headers, self.scrub)
            if 300 <= status < 400 and call.succeeded(status):
                return Answer(status, b"", "", kept)
            raise self.refusal(status, body or b"", call, mutating=mutating, headers=kept) from None
        except PinnedPeerError as exc:
            # Raised while resolving and pinning, before anything was sent.
            host = request.host
            if "cannot be resolved" in str(exc):
                raise ExtensionError(
                    errors.CONNECTION_FAILED,
                    f"{host} could not be resolved",
                    failure_class="transient",
                    retryable=True,
                    definitely_no_external_effect=True,
                    external_effect_status="failed",
                ) from None
            raise errors.no_effect(
                errors.BLOCKED_ADDRESS,
                f"{host} is not reachable under the host network policy",
            ) from None
        except TimeoutError:
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.TIMEOUT,
                "YouTube did not answer in time" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        except (OSError, http.client.HTTPException):
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.CONNECTION_FAILED,
                "The connection to YouTube failed" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        kept = _kept_headers(headers, self.scrub)
        if status < 200 or status >= 300:
            raise self.refusal(
                status, raw[:MAX_ERROR_BODY_BYTES], call, mutating=mutating, headers=kept
            )
        if not call.succeeded(status):
            raise undocumented(status, call, mutating=mutating)
        return Answer(status, raw, _media(headers), kept)

    # -- refusals ------------------------------------------------------------

    def google_error(self, raw: bytes) -> Mapping[str, Any] | None:
        """Google's error object of ``raw`` (``{"error": {"code", "message", ...}}``), or
        None when ``raw`` is not one."""
        try:
            data = parse_json(raw)
        except ValueError:
            return None
        if not isinstance(data, Mapping) or not isinstance(data.get("error"), Mapping):
            return None
        error = data["error"]
        code = error.get("code")
        if isinstance(code, bool) or not isinstance(code, int):
            return None
        if not isinstance(error.get("message"), str):
            return None
        return error

    def error_form(self, raw: bytes, status: int) -> bool:
        """True when ``raw`` is Google's error object for HTTP ``status``."""
        error = self.google_error(raw)
        return error is not None and error.get("code") == status

    def reasons(self, raw: bytes) -> list[str]:
        """The ``errors[].reason`` values of Google's error object (at most 5)."""
        error = self.google_error(raw)
        items = error.get("errors") if error is not None else None
        out: list[str] = []
        if isinstance(items, list):
            for item in items[:5]:
                reason = item.get("reason") if isinstance(item, Mapping) else None
                if isinstance(reason, str) and reason.strip():
                    out.append(errors.safe_text(self.scrub(reason), 80))
        return out

    def detail(self, raw: bytes) -> str:
        """YouTube's own words about a refusal; never the token."""
        try:
            data = self.scrub(parse_json(raw))
        except ValueError:
            text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
            return errors.safe_text(self.scrub(text), 200)
        if not isinstance(data, Mapping):
            return errors.safe_text(data, 200)
        error = data.get("error")
        parts: list[str] = []
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                parts.append(errors.safe_text(message, 400))
            items = error.get("errors")
            if isinstance(items, list):
                for item in items[:3]:
                    if not isinstance(item, Mapping):
                        continue
                    reason = item.get("reason")
                    where = item.get("location")
                    text = errors.safe_text(reason, 80) if isinstance(reason, str) else ""
                    if isinstance(where, str) and where.strip():
                        text += f" (at {errors.safe_text(where, 100)})"
                    if text:
                        parts.append(text)
        elif isinstance(error, str) and error.strip():
            parts.append(error.strip())
            description = data.get("error_description")
            if isinstance(description, str) and description.strip():
                parts.append(description.strip())
        return errors.safe_text("; ".join(parts), 900)

    def refusal(
        self,
        status: int,
        raw: bytes,
        call: Call,
        *,
        mutating: bool,
        headers: Mapping[str, str] | None = None,
    ) -> ExtensionError:
        shown = call.shown
        detail = self.detail(raw)
        suffix = f": {detail}" if detail else ""
        retry_after = parse_retry_after((headers or {}).get("Retry-After"))
        reasons = set(self.reasons(raw))
        certain = (
            not mutating or status == 429 or (400 <= status < 500 and self.error_form(raw, status))
        )
        if status == 429 or (status == 403 and reasons & QUOTA_REASONS):
            code = errors.RATE_LIMITED
            wait = f"; YouTube asks to wait {int(retry_after)} s" if retry_after else ""
            what = (
                "the project's YouTube quota is used up"
                if "quotaExceeded" in reasons or "dailyLimitExceeded" in reasons
                else "a rate limit is reached"
            )
            message = f"YouTube refused {shown}: {what} (HTTP {status}){wait}{suffix}"
        elif status in {401, 403}:
            code = errors.AUTHENTICATION_FAILED
            message = (
                f"YouTube refused {shown} (HTTP {status}){suffix}. The authorization expired or "
                "was withdrawn, the connection lacks the Google scope this step needs, or the "
                "account may not do this; connect again on the YouTube page or use a "
                "connection type with that scope"
            )
        elif 300 <= status < 400:
            code = errors.REDIRECT_REJECTED
            message = f"YouTube redirected {shown} (HTTP {status}); redirects are not followed"
        elif status == 404:
            code = errors.NOT_FOUND
            message = f"YouTube found nothing for {shown} (HTTP 404){suffix}"
        elif status == 409:
            code = errors.CONFLICT
            message = f"YouTube refused {shown} as a conflict (HTTP 409){suffix}"
        elif status in {400, 412, 422}:
            code = errors.UPSTREAM_VALIDATION_FAILED
            message = f"YouTube refused {shown} (HTTP {status}){suffix}"
        elif status >= 500 or status == 408:
            code = errors.TIMEOUT if status in {408, 504} else errors.UPSTREAM_FAILURE
            message = f"YouTube could not complete {shown} (HTTP {status}){suffix}"
        else:
            code = errors.UPSTREAM_VALIDATION_FAILED
            message = f"YouTube rejected {shown} (HTTP {status}){suffix}"
        if not certain:
            return unknown(message + CHECK, code, status)
        if mutating:
            message += "; nothing was changed"
        return ExtensionError(
            code,
            message,
            failure_class="provider",
            retryable=not mutating and (status >= 500 or status in {408, 429}),
            definitely_no_external_effect=True,
            external_effect_status="failed",
            http_status=status,
            retry_after_seconds=retry_after if status == 429 and not mutating else None,
        )


def undocumented(status: int, call: Call, *, mutating: bool) -> ExtensionError:
    """An answer outside the call's success statuses: not taken as success."""
    documented = ", ".join(call.success) or "none"
    message = (
        f"YouTube answered {call.shown} with HTTP {status}, which is not a success for this "
        f"request (expected: {documented})"
    )
    if mutating:
        return unknown(message + CHECK, errors.INVALID_RESPONSE, status)
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        message,
        failure_class="provider",
        retryable=False,
        http_status=status,
    )


def unknown(message: str, code: str, status: int | None) -> ExtensionError:
    return ExtensionError(
        code,
        message,
        failure_class="provider",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=status,
    )


def _session_url(url: str, base: str) -> str:
    """An upload session address: only on the API host the upload started on."""
    if not url.startswith(base + "/") or any(ch in url for ch in " \r\n\t#"):
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            "YouTube returned an upload address outside its API host; nothing was uploaded",
            failure_class="provider",
            retryable=False,
        )
    return url


def _media(headers: Any) -> str:
    kind = str(headers.get("Content-Type") or "") if hasattr(headers, "get") else ""
    return kind.split(";")[0].strip().lower()


def _kept_headers(headers: Any, scrub: Callable[[Any], Any]) -> dict[str, str]:
    """The headers a step may return, the token removed before they are bounded (so a
    cut never leaves part of it)."""
    kept: dict[str, str] = {}
    if headers is None or not hasattr(headers, "get"):
        return kept
    for name in KEPT_HEADERS:
        value = headers.get(name)
        if isinstance(value, str) and value.strip():
            kept[name] = errors.safe_text(scrub(value), 2000)
    return kept


def dumps_json(value: Any) -> str:
    """JSON with ``Decimal`` written as an exact number (never through float).

    A Decimal outside ``numbers``' bounds is written as text in its own exponential
    notation, never expanded."""
    marker = secrets.token_hex(8)

    def default(item: Any) -> str:
        if isinstance(item, Decimal) and numbers.bounded(item):
            return f"@{marker}@{format(item, 'f')}@{marker}@"
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError(f"{type(item).__name__} is not JSON")

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=default)
    return re.sub(rf'"@{marker}@([-+0-9.]+)@{marker}@"', r"\1", text)


def _answer_number(integer: bool) -> Callable[[str], Any]:
    def read(text: str) -> Any:
        number = numbers.read(text, integer=integer)
        # Outside the bounds: kept as YouTube wrote it, as text, never expanded.
        return text if number is None else number

    return read


_ANSWER_FLOAT = _answer_number(False)
_ANSWER_INT = _answer_number(True)


class TooDeep(ValueError):
    """YouTube's answer nests deeper than ``nesting.MAX_ANSWER_DEPTH``; it is not read."""


def parse_json(raw: bytes) -> Any:
    """Any JSON value, numbers with a point read as Decimal; ValueError otherwise.

    A number outside ``numbers``' bounds (and NaN or Infinity) is kept as the text
    YouTube wrote, so reading it never expands it or fails on it. An answer nested
    deeper than ``nesting.MAX_ANSWER_DEPTH`` (counted on the bytes, before parsing) is
    ``TooDeep`` and never reaches the JSON reader, so no RecursionError comes out."""
    if nesting.too_deep(raw, nesting.MAX_ANSWER_DEPTH):
        raise TooDeep(f"nested deeper than {nesting.MAX_ANSWER_DEPTH} levels")
    try:
        text = raw.decode("utf-8-sig", "strict") if raw else ""
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8") from exc
    if not text.strip():
        raise ValueError("empty")
    try:
        return json.loads(
            text, parse_float=_ANSWER_FLOAT, parse_int=_ANSWER_INT, parse_constant=str
        )
    except json.JSONDecodeError as exc:
        raise ValueError("bad JSON") from exc
    except RecursionError as exc:  # pragma: no cover - the depth check comes first
        raise TooDeep("nested too deeply") from exc


def read_bounded(
    response: Any,
    limit: int,
    *,
    mutating: bool = False,
    expires: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    per_read: float | None = None,
) -> bytes:
    """Read at most ``limit`` bytes before ``expires``; a longer answer is an error."""
    buffer = bytearray()
    sock = _socket_of(response)
    while True:
        if expires is not None:
            left = expires - clock()
            if left <= 0:
                _late(mutating)
            if sock is not None:
                try:
                    sock.settimeout(max(0.5, min(left, per_read or left)))
                except OSError:  # pragma: no cover - a closed socket fails the read below
                    pass
        chunk = response.read(min(CHUNK_BYTES, limit + 1 - len(buffer)))
        if not chunk:
            break
        buffer.extend(chunk)
        if expires is not None and clock() > expires:
            _late(mutating)
        if len(buffer) > limit:
            if mutating:
                raise unknown(
                    "YouTube's answer was too large to read" + CHECK,
                    errors.RESPONSE_TOO_LARGE,
                    None,
                )
            raise errors.no_effect(
                errors.RESPONSE_TOO_LARGE,
                f"YouTube's answer is larger than the {limit // (1024 * 1024)} MB this extension "
                "reads; narrow the request",
            )
    return bytes(buffer)


def _late(mutating: bool) -> None:
    if not mutating:
        raise DeadlineReached
    raise ExtensionError(
        errors.TIMEOUT_UNKNOWN,
        "YouTube's answer did not arrive in time" + CHECK,
        failure_class="transient",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
    )


def _socket_of(response: Any) -> Any:
    for path in (("fp", "raw", "_sock"), ("fp", "fp", "raw", "_sock"), ("_sock",)):
        node = response
        for name in path:
            node = getattr(node, name, None)
        if node is not None and hasattr(node, "settimeout"):
            return node
    return None


def _transport_failure_facts(*, mutating: bool) -> dict[str, Any]:
    return {
        "failure_class": "transient",
        "retryable": not mutating,
        "definitely_no_external_effect": not mutating,
        "external_effect_status": "timeout_unknown" if mutating else "failed",
    }


__all__ = [
    "CHECK",
    "MAX_FILE_ANSWER_BYTES",
    "MIN_CALL_WINDOW_SECONDS",
    "YouTubeTransport",
    "Answer",
    "Call",
    "DeadlineReached",
    "TooDeep",
    "dumps_json",
    "parse_json",
    "read_bounded",
    "undocumented",
    "unknown",
]
