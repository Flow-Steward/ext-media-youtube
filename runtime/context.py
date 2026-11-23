"""One invocation's ports: its input, its YouTube transport and the artifact plane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .connection import Connection
from .transport import YouTubeTransport

TransportFactory = Callable[[Connection], YouTubeTransport]
ArtifactReader = Callable[..., bytes]
ArtifactWriter = Callable[..., Mapping[str, Any]]


class Context:
    """One invocation: its input, its connection's transport and the artifact plane."""

    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        operation_input: Mapping[str, Any],
        transport: YouTubeTransport,
        artifact_reader: ArtifactReader,
        artifact_writer: ArtifactWriter,
    ) -> None:
        self.payload = payload
        self.operation_input = operation_input
        self.transport = transport
        self.artifact_reader = artifact_reader
        self.artifact_writer = artifact_writer

    @property
    def connection(self) -> Connection:
        return self.transport.connection
