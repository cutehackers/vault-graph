from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.errors import (
    CatalogError,
    ContextPackError,
    GraphStoreError,
    KeywordIndexError,
    ReadOnlyBoundaryError,
    ResultExplanationError,
    SearchError,
    TextEmbeddingsError,
    VaultGraphError,
    VectorStoreError,
)

McpErrorSeverity = Literal["info", "warning", "error"]
McpProtocolErrorKind = Literal["invalid_parameter", "not_found", "execution", "internal"]
ABSOLUTE_PATH_RE = re.compile(r"(?P<path>(?:/[^\s:;,)\]]+)+|[A-Za-z]:\\[^\s:;,)\]]+)")


@dataclass(frozen=True)
class McpErrorPayload:
    code: str
    message: str
    severity: McpErrorSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None


class McpProtocolError(Exception):
    def __init__(self, *, kind: McpProtocolErrorKind, payload: McpErrorPayload) -> None:
        super().__init__(payload.message)
        self.kind = kind
        self.payload = payload


def map_exception_to_mcp_error(
    exc: Exception,
    *,
    affected_vault_ids: tuple[str, ...] = (),
    user_state_path: Path | None = None,
) -> McpProtocolError:
    if isinstance(exc, CatalogError):
        return _error(
            "invalid_parameter",
            "catalog_error",
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, ReadOnlyBoundaryError):
        return _error(
            "execution",
            "read_only_boundary_error",
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, GraphStoreError):
        code = _code_for_domain_error(exc)
        return _error(
            _kind_for_domain_code(code),
            code,
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, (KeywordIndexError, VectorStoreError, TextEmbeddingsError)):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, (SearchError, ContextPackError)):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    if isinstance(exc, ResultExplanationError):
        code = _code_for_domain_error(exc)
        return _error(
            _kind_for_domain_code(code),
            code,
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
            recovery_hint=(
                "Rerun the original MCP tool and pass a result_id from the new response."
                if code == "result_explanation_not_found"
                else None
            ),
        )
    if isinstance(exc, VaultGraphError):
        return _error(
            "execution",
            _code_for_domain_error(exc),
            _sanitize_error_message(str(exc), user_state_path=user_state_path),
            affected_vault_ids,
        )
    return _error(
        "internal",
        "internal_error",
        _sanitize_internal_message(exc, user_state_path=user_state_path),
        affected_vault_ids,
        recovery_hint="Check stderr logs and rerun the command with the same --state path.",
    )


def _error(
    kind: McpProtocolErrorKind,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> McpProtocolError:
    return McpProtocolError(
        kind=kind,
        payload=McpErrorPayload(
            code=code,
            message=message,
            severity="error",
            affected_vault_ids=affected_vault_ids,
            recovery_hint=recovery_hint,
        ),
    )


def _code_for_domain_error(exc: Exception) -> str:
    message = str(exc)
    if ":" in message:
        prefix = message.split(":", 1)[0].strip()
        if prefix in {
            "graph_unavailable",
            "resource_not_found",
            "ambiguous_resource",
            "metadata_unavailable",
            "memory_projection_unavailable",
            "memory_evidence_unresolved",
            "invalid_memory_evidence_limit",
            "invalid_memory_limit",
            "resource_not_available",
            "result_explanation_not_found",
            "invalid_result_id",
        }:
            return prefix
    name = exc.__class__.__name__
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _kind_for_domain_code(code: str) -> McpProtocolErrorKind:
    if code == "resource_not_found":
        return "not_found"
    if code == "result_explanation_not_found":
        return "not_found"
    if code == "ambiguous_resource":
        return "invalid_parameter"
    if code == "invalid_result_id":
        return "invalid_parameter"
    return "execution"


def _sanitize_internal_message(exc: Exception, *, user_state_path: Path | None) -> str:
    text = str(exc)
    sanitized = _sanitize_error_message(text, user_state_path=user_state_path)
    return sanitized if sanitized != text else "unexpected MCP server error"


def _sanitize_error_message(message: str, *, user_state_path: Path | None) -> str:
    allowed_state = str(user_state_path.expanduser().resolve()) if user_state_path is not None else None

    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        if allowed_state is not None and (path == allowed_state or path.startswith(f"{allowed_state}/")):
            return path
        return "<redacted-path>"

    return ABSOLUTE_PATH_RE.sub(replace, message)
