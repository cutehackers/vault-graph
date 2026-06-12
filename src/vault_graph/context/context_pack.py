from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import ContextPackError
from vault_graph.ingestion.vault_catalog import QueryScope

CONTEXT_PACK_SCHEMA_VERSION = "context-pack-v1"
DEFAULT_CONTEXT_MAX_TOKENS = 8000
DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS = 24
DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS = 320
DEFAULT_CONTEXT_RETRIEVAL_LIMIT = 10
DEFAULT_RETRIEVAL_POLICY_VERSION = "retrieval-policy-v1"

ContextPackRevisionKind = Literal["git", "snapshot", "unknown"]
ContextPackStoreRevisionKind = Literal["metadata", "keyword", "vector", "graph", "projection"]
ContextPackItemType = Literal["current_state", "page", "source", "decision", "constraint", "open_question"]
ContextPackSignalKind = Literal["keyword", "vector", "graph"]
ContextPackWarningSeverity = Literal["info", "warning", "error"]
ContextPackWarningSourceKind = Literal["retrieval", "graph", "budget", "builder"]

_REVISION_KINDS = {"git", "snapshot", "unknown"}
_STORE_REVISION_KINDS = {"metadata", "keyword", "vector", "graph", "projection"}
_ITEM_TYPES = {"current_state", "page", "source", "decision", "constraint", "open_question"}
_SIGNAL_KINDS = {"keyword", "vector", "graph"}
_WARNING_SEVERITIES = {"info", "warning", "error"}
_WARNING_SOURCE_KINDS = {"retrieval", "graph", "budget", "builder"}


@dataclass(frozen=True)
class ContextPackVault:
    vault_id: str
    display_name: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.display_name, "display_name")


@dataclass(frozen=True)
class ContextPackVaultRevision:
    vault_id: str
    revision: str | None
    revision_kind: ContextPackRevisionKind

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        if self.revision_kind not in _REVISION_KINDS:
            raise ContextPackError("unsupported vault revision kind")


@dataclass(frozen=True)
class ContextPackRequestedScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...]
    include_cross_vault: bool

    def __post_init__(self) -> None:
        _require_tuple(self.vault_ids, "vault_ids")
        _require_tuple(self.content_scopes, "content_scopes")


@dataclass(frozen=True)
class ContextPackActualScope:
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...]
    include_cross_vault: bool
    scope_key: str

    def __post_init__(self) -> None:
        _require_tuple(self.vault_ids, "vault_ids")
        _require_tuple(self.content_scopes, "content_scopes")
        _require_non_empty(self.scope_key, "scope_key")


@dataclass(frozen=True)
class ContextPackScope:
    requested: ContextPackRequestedScope
    actual_scopes: tuple[ContextPackActualScope, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.actual_scopes, tuple):
            raise ContextPackError("actual_scopes must be an immutable tuple")


@dataclass(frozen=True)
class ContextPackStoreRevision:
    kind: ContextPackStoreRevisionKind
    revision: str | None
    vault_id: str | None
    scope_key: str

    def __post_init__(self) -> None:
        if self.kind not in _STORE_REVISION_KINDS:
            raise ContextPackError("unsupported store revision kind")
        _require_non_empty(self.scope_key, "scope_key")


@dataclass(frozen=True)
class ContextPackBackendUse:
    name: str | None
    used: bool


@dataclass(frozen=True)
class ContextPackBackend:
    metadata_store: ContextPackBackendUse
    keyword_index: ContextPackBackendUse
    vector_store: ContextPackBackendUse
    graph_store: ContextPackBackendUse
    graph_projection: ContextPackBackendUse


@dataclass(frozen=True)
class ContextEvidenceRef:
    vault_id: str
    document_id: str
    chunk_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.document_id, "document_id")
        _require_non_empty(self.chunk_id, "chunk_id")


@dataclass(frozen=True)
class ContextPackWarning:
    code: str
    severity: ContextPackWarningSeverity
    message: str
    affected_vault_ids: tuple[str, ...]
    evidence_refs: tuple[ContextEvidenceRef, ...] = ()
    scope_key: str | None = None
    source_code: str | None = None
    source_kind: ContextPackWarningSourceKind | None = None
    entity_id: str | None = None
    relationship_id: str | None = None
    evidence_ref_id: str | None = None
    recovery_hint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")
        _require_tuple(self.affected_vault_ids, "affected_vault_ids")
        if self.severity not in _WARNING_SEVERITIES:
            raise ContextPackError("unsupported warning severity")
        if self.source_kind is not None and self.source_kind not in _WARNING_SOURCE_KINDS:
            raise ContextPackError("unsupported warning source kind")
        if not isinstance(self.evidence_refs, tuple):
            raise ContextPackError("evidence_refs must be an immutable tuple")


@dataclass(frozen=True)
class ContextEvidence:
    ref: ContextEvidenceRef
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    raw_sha256: str | None
    metadata_index_revision: str
    vault_revision: str | None
    excerpt: str
    excerpt_token_count: int
    truncated: bool
    retrieval_reasons: tuple[str, ...]
    warnings: tuple[ContextPackWarning, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.path, "path")
        _require_non_empty(self.content_hash, "content_hash")
        _require_non_empty(self.metadata_index_revision, "metadata_index_revision")
        if self.excerpt_token_count < 0:
            raise ContextPackError("excerpt_token_count must not be negative")
        if self.truncated and not any(warning.code == "excerpt_truncated" for warning in self.warnings):
            raise ContextPackError("truncated evidence requires excerpt_truncated warning")
        if not isinstance(self.retrieval_reasons, tuple):
            raise ContextPackError("retrieval_reasons must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise ContextPackError("warnings must be an immutable tuple")


@dataclass(frozen=True)
class ContextPackSignal:
    kind: ContextPackSignalKind
    rank: int | None
    score: float | None
    explanation: str

    def __post_init__(self) -> None:
        if self.kind not in _SIGNAL_KINDS:
            raise ContextPackError("unsupported signal kind")
        _require_non_empty(self.explanation, "explanation")
        if self.rank is not None and self.rank <= 0:
            raise ContextPackError("signal rank must be positive")


@dataclass(frozen=True)
class ContextPackItem:
    item_id: str
    item_type: ContextPackItemType
    title: str
    summary: str
    evidence_refs: tuple[ContextEvidenceRef, ...]
    retrieval_signals: tuple[ContextPackSignal, ...]
    relationship_status: str | None
    rank: int
    warnings: tuple[ContextPackWarning, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.title, "title")
        if self.item_type not in _ITEM_TYPES:
            raise ContextPackError("unsupported item type")
        if not self.evidence_refs:
            raise ContextPackError("evidence_refs are required")
        if not isinstance(self.evidence_refs, tuple):
            raise ContextPackError("evidence_refs must be an immutable tuple")
        if not isinstance(self.retrieval_signals, tuple):
            raise ContextPackError("retrieval_signals must be an immutable tuple")
        if not isinstance(self.warnings, tuple):
            raise ContextPackError("warnings must be an immutable tuple")
        if self.rank <= 0:
            raise ContextPackError("item rank must be positive")


@dataclass(frozen=True)
class ContextPackBudget:
    max_tokens: int = DEFAULT_CONTEXT_MAX_TOKENS
    max_evidence_items: int = DEFAULT_CONTEXT_MAX_EVIDENCE_ITEMS
    max_excerpt_tokens: int = DEFAULT_CONTEXT_MAX_EXCERPT_TOKENS
    used_tokens: int = 0
    omitted_items: int = 0

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ContextPackError("max_tokens must be positive")
        if self.max_evidence_items <= 0:
            raise ContextPackError("max_evidence_items must be positive")
        if self.max_excerpt_tokens <= 0:
            raise ContextPackError("max_excerpt_tokens must be positive")
        if self.used_tokens < 0:
            raise ContextPackError("used_tokens must not be negative")
        if self.omitted_items < 0:
            raise ContextPackError("omitted_items must not be negative")


@dataclass(frozen=True)
class ContextPackRequest:
    goal: str
    requested_scope: QueryScope
    budget: ContextPackBudget = ContextPackBudget()
    retrieval_limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    include_graph: bool = False
    include_cross_vault: bool = False

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ContextPackError("goal is required")
        if self.retrieval_limit <= 0:
            raise ContextPackError("retrieval_limit must be positive")
        if self.include_cross_vault != self.requested_scope.include_cross_vault:
            raise ContextPackError("include_cross_vault must match requested_scope.include_cross_vault")
        if self.include_cross_vault and not self.include_graph:
            raise ContextPackError("include_cross_vault requires include_graph")
        if self.include_cross_vault and len(self.requested_scope.vault_ids) <= 1:
            raise ContextPackError("include_cross_vault requires multiple requested vault_ids")


@dataclass(frozen=True)
class ContextPack:
    context_pack_schema_version: str
    pack_id: str
    goal: str
    scope: ContextPackScope
    vaults: tuple[ContextPackVault, ...]
    vault_revisions: tuple[ContextPackVaultRevision, ...]
    backend: ContextPackBackend
    store_revisions: tuple[ContextPackStoreRevision, ...]
    retrieval_policy_version: str
    budget: ContextPackBudget
    generated_at: str
    current_state: tuple[ContextPackItem, ...]
    relevant_pages: tuple[ContextPackItem, ...]
    relevant_sources: tuple[ContextPackItem, ...]
    decisions: tuple[ContextPackItem, ...]
    constraints: tuple[ContextPackItem, ...]
    open_questions: tuple[ContextPackItem, ...]
    warnings: tuple[ContextPackWarning, ...]
    evidence: tuple[ContextEvidence, ...]

    def __post_init__(self) -> None:
        if self.context_pack_schema_version != CONTEXT_PACK_SCHEMA_VERSION:
            raise ContextPackError("context_pack_schema_version must match current schema")
        if not self.goal.strip():
            raise ContextPackError("goal is required")
        _require_non_empty(self.retrieval_policy_version, "retrieval_policy_version")
        _require_non_empty(self.generated_at, "generated_at")
        for field_name in (
            "vaults",
            "vault_revisions",
            "store_revisions",
            "current_state",
            "relevant_pages",
            "relevant_sources",
            "decisions",
            "constraints",
            "open_questions",
            "warnings",
            "evidence",
        ):
            if not isinstance(getattr(self, field_name), tuple):
                raise ContextPackError(f"{field_name} must be an immutable tuple")


def context_scope_from_query_scopes(
    *,
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
) -> ContextPackScope:
    return ContextPackScope(
        requested=ContextPackRequestedScope(
            vault_ids=requested_scope.vault_ids,
            content_scopes=requested_scope.content_scopes,
            include_cross_vault=requested_scope.include_cross_vault,
        ),
        actual_scopes=tuple(
            ContextPackActualScope(
                vault_ids=actual_scope.vault_ids,
                content_scopes=actual_scope.content_scopes,
                include_cross_vault=actual_scope.include_cross_vault,
                scope_key=scope_key(actual_scope),
            )
            for actual_scope in actual_scopes
        ),
    )


def scope_key(scope: QueryScope) -> str:
    suffix = "cross-vault" if scope.include_cross_vault else "local"
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{suffix}"


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ContextPackError(f"{field_name} is required")


def _require_tuple(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise ContextPackError(f"{field_name} must be an immutable tuple")
    if not value:
        raise ContextPackError(f"{field_name} is required")
    if any(not item for item in value):
        raise ContextPackError(f"{field_name} contains an empty value")
