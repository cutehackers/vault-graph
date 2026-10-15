from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from vault_graph.errors import ResultExplanationError

ExplanationSourceKind = Literal[
    "search_result",
    "context_pack_item",
    "related_item",
    "decision_trace_step",
]
ExplanationWarningSeverity = Literal["info", "warning", "error"]

_SOURCE_KINDS = {"search_result", "context_pack_item", "related_item", "decision_trace_step"}
_WARNING_SEVERITIES = {"info", "warning", "error"}


@dataclass(frozen=True)
class ExplanationEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str | None
    vault_revision: str | None

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")
        _require_non_empty(self.path, "path")
        _require_non_empty(self.content_hash, "content_hash")


@dataclass(frozen=True)
class ExplanationSignal:
    kind: str
    source_id: str | None
    rank: int | None
    score: float | None
    backend: str | None
    index_revision: str | None
    explanation: str

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "signal kind")
        _require_non_empty(self.explanation, "signal explanation")
        if self.rank is not None and self.rank <= 0:
            raise ResultExplanationError("signal rank must be positive")


@dataclass(frozen=True)
class ExplanationWarning:
    code: str
    message: str
    severity: ExplanationWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "warning code")
        _require_non_empty(self.message, "warning message")
        if self.severity not in _WARNING_SEVERITIES:
            raise ResultExplanationError("unsupported warning severity")
        if not isinstance(self.affected_vault_ids, tuple):
            raise ResultExplanationError("affected_vault_ids must be an immutable tuple")
        if not self.affected_vault_ids:
            raise ResultExplanationError("affected_vault_ids is required")
        for vault_id in self.affected_vault_ids:
            _require_non_empty(vault_id, "affected vault_id")


@dataclass(frozen=True)
class ExplanationRecord:
    result_id: str
    source_kind: ExplanationSourceKind
    title: str
    summary: str
    vault_id: str
    evidence: tuple[ExplanationEvidenceRef, ...]
    signals: tuple[ExplanationSignal, ...]
    relationship_status: str | None
    store_revisions: tuple[dict[str, object], ...]
    warnings: tuple[ExplanationWarning, ...]
    resource_links: tuple[dict[str, object], ...]
    generated_at: str

    def __post_init__(self) -> None:
        _require_non_empty(self.result_id, "result_id")
        if self.source_kind not in _SOURCE_KINDS:
            raise ResultExplanationError("unsupported explanation source_kind")
        _require_non_empty(self.title, "title")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.generated_at, "generated_at")
        _require_tuple(self.evidence, "evidence")
        if not self.evidence:
            raise ResultExplanationError("evidence is required")
        _require_tuple(self.signals, "signals")
        _require_tuple(self.store_revisions, "store_revisions")
        _require_tuple(self.warnings, "warnings")
        _require_tuple(self.resource_links, "resource_links")
        for revision in self.store_revisions:
            _validate_json_safe_mapping(revision, field_name="store_revisions")
        for link in self.resource_links:
            _validate_resource_link(link)


class CachedExplanationView(Protocol):
    record: ExplanationRecord
    cached_at: str


class ExplanationCacheReader(Protocol):
    def get(self, result_id: str) -> CachedExplanationView | None: ...


class ExplainResultService:
    def __init__(self, *, cache: ExplanationCacheReader) -> None:
        self._cache = cache

    def explain(self, *, result_id: str) -> ExplanationRecord:
        stripped = result_id.strip() if isinstance(result_id, str) else ""
        if not stripped:
            raise ResultExplanationError("invalid_result_id: result_id is required")
        cached = self._cache.get(stripped)
        if cached is None:
            raise ResultExplanationError(
                "result_explanation_not_found: rerun the original MCP tool and retry explain_result"
            )
        return cached.record


def explanation_record_to_dict(record: ExplanationRecord) -> dict[str, object]:
    return {
        "result_id": record.result_id,
        "source_kind": record.source_kind,
        "title": record.title,
        "summary": record.summary,
        "vault_id": record.vault_id,
        "evidence": [_evidence_ref_to_dict(evidence) for evidence in record.evidence],
        "signals": [_signal_to_dict(signal) for signal in record.signals],
        "relationship_status": record.relationship_status,
        "store_revisions": [dict(revision) for revision in record.store_revisions],
        "warnings": [_warning_to_dict(warning) for warning in record.warnings],
        "resource_links": [dict(link) for link in record.resource_links],
        "generated_at": record.generated_at,
    }


def _evidence_ref_to_dict(evidence: ExplanationEvidenceRef) -> dict[str, object]:
    return {
        "vault_id": evidence.vault_id,
        "document_id": evidence.document_id,
        "chunk_id": evidence.chunk_id,
        "path": evidence.path,
        "section": evidence.section,
        "anchor": evidence.anchor,
        "content_hash": evidence.content_hash,
        "raw_sha256": evidence.raw_sha256,
        "metadata_index_revision": evidence.metadata_index_revision,
        "vault_revision": evidence.vault_revision,
    }


def _signal_to_dict(signal: ExplanationSignal) -> dict[str, object]:
    return {
        "kind": signal.kind,
        "source_id": signal.source_id,
        "rank": signal.rank,
        "score": signal.score,
        "backend": signal.backend,
        "index_revision": signal.index_revision,
        "explanation": signal.explanation,
    }


def _warning_to_dict(warning: ExplanationWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }


def _validate_resource_link(value: dict[str, object]) -> None:
    _validate_json_safe_mapping(value, field_name="resource_links")
    rel = value.get("rel")
    uri = value.get("uri")
    if not isinstance(rel, str) or not rel.strip():
        raise ResultExplanationError("resource_links entries require rel")
    if not isinstance(uri, str) or not uri.strip():
        raise ResultExplanationError("resource_links entries require uri")


def _validate_json_safe_mapping(value: dict[str, object], *, field_name: str) -> None:
    if not isinstance(value, dict):
        raise ResultExplanationError(f"{field_name} entries must be dictionaries")
    for key, item in value.items():
        if not isinstance(key, str):
            raise ResultExplanationError(f"{field_name} keys must be strings")
        _validate_json_safe_value(item, field_name=field_name)


def _validate_json_safe_value(value: object, *, field_name: str) -> None:
    if isinstance(value, str | int | float | bool) or value is None:
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_json_safe_value(item, field_name=field_name)
        return
    if isinstance(value, dict):
        _validate_json_safe_mapping(value, field_name=field_name)
        return
    raise ResultExplanationError(f"{field_name} entries must be JSON-safe")


def _require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise ResultExplanationError(f"{field_name} must be an immutable tuple")


def _require_non_empty(value: str | None, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResultExplanationError(f"{field_name} is required")
