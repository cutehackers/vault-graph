"""Resource body and resource link records shared by MCP tools, resources, readers and serializers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.interface.mcp.mcp_errors import McpErrorPayload

McpResourceContentMime = Literal["text/markdown", "application/json"]


@dataclass(frozen=True)
class McpResourceBody:
    uri: str
    content_mime_type: McpResourceContentMime
    text: str
    metadata: dict[str, object]
    warnings: tuple[McpErrorPayload, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "content_mime_type": self.content_mime_type,
            "text": self.text,
            "metadata": self.metadata,
            "warnings": [
                {
                    "code": warning.code,
                    "message": warning.message,
                    "severity": warning.severity,
                    "affected_vault_ids": list(warning.affected_vault_ids),
                    "recovery_hint": warning.recovery_hint,
                }
                for warning in self.warnings
            ],
        }


@dataclass(frozen=True)
class McpResourceLink:
    rel: str
    uri: str
    title: str | None = None
    vault_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    repository_id: str | None = None
    relative_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "rel": self.rel,
            "uri": self.uri,
            "title": self.title,
            "vault_id": self.vault_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "repository_id": self.repository_id,
            "relative_path": self.relative_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }
