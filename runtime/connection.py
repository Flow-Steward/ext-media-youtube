"""Project-scoped YouTube connection: one Google account's YouTube channel.

Flow Steward Core runs the OAuth 2.0 authorization code flow with PKCE (ADR 0023)
against Google's endpoints that this extension declares in ``extension.yaml``, the
same way the Flow Steward Google Workspace extension does: Core keeps the Client
Secret and the refresh token, refreshes the access token and stores it. A step
receives only the current access token, in ``target.connection.secrets.access_token``;
this extension never sees the refresh token or the client secret and never mints,
stores or refreshes a token itself.

The three connection types differ only in the Google scopes Core asks for (see
``contracts/connection_types.yaml``); they reach the same hosts.

The token lives in a private field of a frozen dataclass whose ``repr`` never shows
it; it travels only in the ``Authorization`` header and is never placed in a result,
a log line or an exception message.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus

from . import errors
from .errors import ExtensionError

#: Connection types of this extension (all reach the same hosts).
CONNECTION_TYPES: frozenset[str] = frozenset(
    {"youtube_channel", "youtube_channel_monetized", "youtube_content_owner"}
)
#: Host of each API (the ``rootUrl`` of each pinned Discovery document).
HOSTS: dict[str, str] = {
    "data": "youtube.googleapis.com",
}
SECRET_FIELDS: frozenset[str] = frozenset({"access_token"})
#: Shorter tokens could not be removed from answers without mangling them.
MIN_TOKEN_LENGTH = 16
MAX_TOKEN_LENGTH = 16384
#: Printable ASCII without spaces: a header value that cannot be split.
_TOKEN_RE = re.compile(r"^[\x21-\x7e]+$")


def secret_forms(secret: str) -> tuple[str, ...]:
    """Every way a secret can appear in a text: as is and encoded, longest first."""
    forms = {
        secret,
        quote_plus(secret, safe=""),
        quote(secret, safe=""),
        json.dumps(secret, ensure_ascii=False)[1:-1],
        html.escape(secret, quote=True),
        html.escape(secret, quote=False),
    }
    # Longest first, so a form that contains another is removed whole.
    return tuple(sorted((f for f in forms if f), key=len, reverse=True))


@dataclass(frozen=True)
class Connection:
    """One validated YouTube connection."""

    connection_id: str
    connection_type: str
    _access_token: str = field(repr=False)

    @property
    def access_token(self) -> str:
        return self._access_token

    def base_url(self, api: str = "data") -> str:
        return "https://" + HOSTS[api]

    def secret_forms(self) -> tuple[str, ...]:
        return secret_forms(self._access_token)

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"Connection(connection_id={self.connection_id!r})"

    __str__ = __repr__


def _invalid(message: str) -> ExtensionError:
    return errors.no_effect(errors.INVALID_CONNECTION, message)


def _token(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise _invalid(
            "The connection has no Google authorization; press Connect again on the YouTube page"
        )
    if (
        len(text) < MIN_TOKEN_LENGTH
        or len(text) > MAX_TOKEN_LENGTH
        or not _TOKEN_RE.fullmatch(text)
    ):
        raise _invalid("The connection's Google authorization is not usable; connect again")
    return text


def connection_from_payload(payload: Mapping[str, Any], *, connection_ref: str) -> Connection:
    """Validate the selected project connection before any outbound request."""
    action = payload.get("action")
    target = action.get("target") if isinstance(action, Mapping) else None
    connection = target.get("connection") if isinstance(target, Mapping) else None
    if not isinstance(connection, Mapping):
        raise _invalid("The selected connection is unavailable")
    connection_id = str(connection.get("connection_id") or "")
    if not connection_id or (connection_ref and connection_id != connection_ref):
        raise _invalid("The selected connection does not match connection_ref")
    connection_type = str(
        connection.get("connection_type_id") or connection.get("connection_type") or ""
    )
    if connection_type not in CONNECTION_TYPES:
        raise _invalid("The selected connection is not a YouTube connection")
    secrets = connection.get("secrets")
    secrets = secrets if isinstance(secrets, Mapping) else {}
    if set(secrets) - SECRET_FIELDS:
        raise _invalid("The connection carries unsupported secrets")
    return Connection(
        connection_id=connection_id,
        connection_type=connection_type,
        _access_token=_token(secrets.get("access_token")),
    )


__all__ = [
    "CONNECTION_TYPES",
    "HOSTS",
    "SECRET_FIELDS",
    "Connection",
    "connection_from_payload",
    "secret_forms",
]
