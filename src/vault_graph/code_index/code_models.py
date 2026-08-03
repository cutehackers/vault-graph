"""Stable contracts for the read-only code projection.

The models in this module are deliberately independent of parsers, SQLite, and
the CLI. They are the single boundary shared by extraction, storage, query,
and orchestration code. Importing this module performs no I/O and never loads a
grammar or watcher backend.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, NewType

CodeRepositoryId = NewType("CodeRepositoryId", str)

CODE_PROJECTION_SCHEMA_VERSION = "code-projection-v1"
CODE_TREE_SITTER_RUNTIME_VERSION = "0.25.2"
CODE_TREE_SITTER_PYTHON_VERSION = "0.25.0"
CODE_DART_GRAMMAR_PACKAGE_VERSION = "0.1.0"
CODE_DART_GRAMMAR_SOURCE = "https://github.com/efrenbl/tree-sitter-dart"
CODE_DART_GRAMMAR_SOURCE_REVISION = "12ba73fbfd0755652d97bd10e76a84c076112d14"
CODE_TREE_SITTER_ABI_VERSION = 15
CODE_DART_GRAMMAR_REVISION = (
    f"tree-sitter-dart-{CODE_DART_GRAMMAR_PACKAGE_VERSION}@{CODE_DART_GRAMMAR_SOURCE_REVISION}"
    f"-abi{CODE_TREE_SITTER_ABI_VERSION}"
)
CODE_PARSER_SPEC_VERSION = (
    "code-parser-spec-v1/"
    f"tree-sitter-{CODE_TREE_SITTER_RUNTIME_VERSION}/"
    f"python-{CODE_TREE_SITTER_PYTHON_VERSION}/"
    f"dart-{CODE_DART_GRAMMAR_PACKAGE_VERSION}@{CODE_DART_GRAMMAR_SOURCE_REVISION}"
    f"-abi{CODE_TREE_SITTER_ABI_VERSION}"
)

CodeSymbolKind = Literal[
    "repository",
    "file",
    "module",
    "class",
    "interface",
    "mixin",
    "function",
    "method",
    "property",
    "test",
]
CODE_SYMBOL_KINDS: tuple[CodeSymbolKind, ...] = (
    "repository",
    "file",
    "module",
    "class",
    "interface",
    "mixin",
    "function",
    "method",
    "property",
    "test",
)

CodeRelationKind = Literal["CONTAINS", "DEFINES", "IMPORTS", "CALLS", "EXTENDS", "IMPLEMENTS", "TESTS"]
CODE_RELATION_KINDS: tuple[CodeRelationKind, ...] = (
    "CONTAINS",
    "DEFINES",
    "IMPORTS",
    "CALLS",
    "EXTENDS",
    "IMPLEMENTS",
    "TESTS",
)

CodeExtractionStatus = Literal["extracted", "inferred", "ambiguous", "unresolved"]
CODE_EXTRACTION_STATUSES: tuple[CodeExtractionStatus, ...] = (
    "extracted",
    "inferred",
    "ambiguous",
    "unresolved",
)

CodeDiagnosticSeverity = Literal["info", "warning", "error"]
CodeFreshnessState = Literal["fresh", "stale", "syncing", "partial", "unavailable", "unknown"]
CODE_FRESHNESS_STATES: tuple[CodeFreshnessState, ...] = (
    "fresh",
    "stale",
    "syncing",
    "partial",
    "unavailable",
    "unknown",
)
CodeIndexMode = Literal["full", "incremental"]
CodeTraversalDirection = Literal["inbound", "outbound"]
CodeOutputFormat = Literal["text", "json"]


@dataclass(frozen=True)
class CodeRepositoryEntry:
    repository_id: str
    root_path: Path
    display_name: str
    enabled: bool
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    languages: tuple[str, ...]
    state_namespace: str
    git_revision_policy: str
    watch: bool

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "include_globs")
        _normalize_tuple_attr(self, "exclude_globs")
        _normalize_tuple_attr(self, "languages")
        _require_non_empty(self.repository_id, "repository_id")
        if not isinstance(self.root_path, Path) or not str(self.root_path):
            raise ValueError("root_path is required")
        _require_non_empty(self.display_name, "display_name")
        _require_bool(self.enabled, "enabled")
        _require_bool(self.watch, "watch")
        for field_name, values in (
            ("include_globs", self.include_globs),
            ("exclude_globs", self.exclude_globs),
            ("languages", self.languages),
        ):
            for value in values:
                _require_non_empty(value, field_name)
        _require_non_empty(self.state_namespace, "state_namespace")
        _require_non_empty(self.git_revision_policy, "git_revision_policy")


@dataclass(frozen=True)
class CodeFileSnapshot:
    repository_id: str
    relative_path: str
    language: str
    content_hash: str
    byte_count: int
    line_count: int
    source_revision: str
    is_test_file: bool
    parser_spec_version: str

    def __post_init__(self) -> None:
        _require_bool(self.is_test_file, "is_test_file")
        _require_non_empty(self.repository_id, "repository_id")
        _require_non_empty(self.relative_path, "relative_path")
        _require_relative_path(self.relative_path)
        _require_non_empty(self.language, "language")
        _require_digest(self.content_hash, "content_hash")
        _require_non_negative(self.byte_count, "byte_count")
        _require_non_negative(self.line_count, "line_count")
        _require_non_empty(self.source_revision, "source_revision")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")


@dataclass(frozen=True)
class CodeFileInput:
    repository_id: str
    relative_path: str
    language: str
    content: bytes
    content_hash: str
    source_revision: str
    is_test_file: bool
    parser_spec_version: str

    def __post_init__(self) -> None:
        _require_bool(self.is_test_file, "is_test_file")
        _require_non_empty(self.repository_id, "repository_id")
        _require_non_empty(self.relative_path, "relative_path")
        _require_relative_path(self.relative_path)
        _require_non_empty(self.language, "language")
        if not isinstance(self.content, bytes):
            raise ValueError("content must be bytes")
        _require_digest(self.content_hash, "content_hash")
        actual_hash = hashlib.sha256(self.content).hexdigest()
        if self.content_hash != actual_hash:
            raise ValueError("content_hash does not match content")
        _require_non_empty(self.source_revision, "source_revision")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")

    def snapshot(self) -> CodeFileSnapshot:
        return CodeFileSnapshot(
            repository_id=self.repository_id,
            relative_path=self.relative_path,
            language=self.language,
            content_hash=self.content_hash,
            byte_count=len(self.content),
            line_count=_line_count(self.content),
            source_revision=self.source_revision,
            is_test_file=self.is_test_file,
            parser_spec_version=self.parser_spec_version,
        )


@dataclass(frozen=True)
class CodeSymbolRecord:
    symbol_id: str
    repository_id: str
    file_id: str
    kind: str
    language_kind: str
    name: str
    qualified_name: str
    signature: str | None
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    content_hash: str
    source_revision: str
    parser_spec_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "symbol_id",
            "repository_id",
            "file_id",
            "kind",
            "language_kind",
            "name",
            "qualified_name",
            "source_revision",
            "parser_spec_version",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.kind not in CODE_SYMBOL_KINDS:
            raise ValueError(f"unsupported symbol kind: {self.kind}")
        _require_digest(self.content_hash, "content_hash")
        _require_line_range(self.start_line, self.end_line)
        _require_non_negative(self.start_column, "start_column")
        _require_non_negative(self.end_column, "end_column")
        if self.start_line == self.end_line and self.end_column < self.start_column:
            raise ValueError("line range columns are invalid")


@dataclass(frozen=True)
class CodeEdgeRecord:
    edge_id: str
    repository_id: str
    source_symbol_id: str
    relation_kind: str
    target_symbol_id: str | None
    unresolved_target_key: str | None
    extraction_status: CodeExtractionStatus
    anchor_start_line: int
    anchor_start_column: int
    parser_spec_version: str

    def __post_init__(self) -> None:
        for field_name in ("edge_id", "repository_id", "source_symbol_id", "relation_kind", "parser_spec_version"):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.relation_kind not in CODE_RELATION_KINDS:
            raise ValueError(f"unsupported relation_kind: {self.relation_kind}")
        if self.extraction_status not in CODE_EXTRACTION_STATUSES:
            raise ValueError(f"unsupported extraction_status: {self.extraction_status}")
        _require_line(self.anchor_start_line, "anchor_start_line")
        _require_non_negative(self.anchor_start_column, "anchor_start_column")
        if self.target_symbol_id is not None and not self.target_symbol_id:
            raise ValueError("target_symbol_id must be non-empty when provided")
        if self.unresolved_target_key is not None and not self.unresolved_target_key:
            raise ValueError("unresolved_target_key must be non-empty when provided")
        if self.extraction_status in ("extracted", "inferred") and self.target_symbol_id is None:
            raise ValueError("resolved extraction status requires target_symbol_id")
        if self.extraction_status in ("ambiguous", "unresolved") and self.target_symbol_id is not None:
            raise ValueError("ambiguous or unresolved edge cannot have target_symbol_id")


@dataclass(frozen=True)
class CodeReferenceRecord:
    reference_id: str
    repository_id: str
    source_file_id: str
    source_symbol_id: str | None
    relation_kind: str
    target_key: str
    anchor_start_line: int
    anchor_start_column: int
    parser_spec_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "reference_id",
            "repository_id",
            "source_file_id",
            "relation_kind",
            "target_key",
            "parser_spec_version",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.source_symbol_id is not None and not self.source_symbol_id:
            raise ValueError("source_symbol_id must be non-empty when provided")
        if self.relation_kind not in CODE_RELATION_KINDS:
            raise ValueError(f"unsupported relation_kind: {self.relation_kind}")
        _require_line(self.anchor_start_line, "anchor_start_line")
        _require_non_negative(self.anchor_start_column, "anchor_start_column")


@dataclass(frozen=True)
class CodeParseDiagnostic:
    diagnostic_id: str
    repository_id: str
    relative_path: str
    severity: CodeDiagnosticSeverity
    code: str
    message: str
    start_line: int | None
    start_column: int | None
    end_line: int | None
    end_column: int | None
    parser_spec_version: str

    def __post_init__(self) -> None:
        for field_name in ("diagnostic_id", "repository_id", "relative_path", "code", "message", "parser_spec_version"):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_relative_path(self.relative_path)
        if self.severity not in ("info", "warning", "error"):
            raise ValueError(f"unsupported severity: {self.severity}")
        _require_optional_range(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
        )


@dataclass(frozen=True)
class CodeParseResult:
    file: CodeFileSnapshot
    symbols: tuple[CodeSymbolRecord, ...]
    references: tuple[CodeReferenceRecord, ...]
    diagnostics: tuple[CodeParseDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "symbols")
        _normalize_tuple_attr(self, "references")
        _normalize_tuple_attr(self, "diagnostics")
        for record in self.symbols:
            if record.repository_id != self.file.repository_id:
                raise ValueError("parsed record repository_id must match file")
            if record.parser_spec_version != self.file.parser_spec_version:
                raise ValueError("parsed symbol parser_spec_version must match file")
            if record.content_hash != self.file.content_hash or record.source_revision != self.file.source_revision:
                raise ValueError("parsed symbol source identity must match file")
        for reference in self.references:
            if reference.repository_id != self.file.repository_id:
                raise ValueError("parsed record repository_id must match file")
            if reference.source_file_id != code_file_identity(self.file.repository_id, self.file.relative_path):
                raise ValueError("parsed reference source_file_id does not match file")
            if not 1 <= reference.anchor_start_line <= self.file.line_count:
                raise ValueError("parsed reference anchor_start_line is outside file range")
            if reference.parser_spec_version != self.file.parser_spec_version:
                raise ValueError("parsed reference parser_spec_version must match file")
            if reference.source_symbol_id is not None and reference.source_symbol_id not in {
                symbol.symbol_id for symbol in self.symbols
            }:
                raise ValueError("parsed reference source_symbol_id does not match a symbol")
        for diagnostic in self.diagnostics:
            if diagnostic.repository_id != self.file.repository_id:
                raise ValueError("parsed record repository_id must match file")
            if diagnostic.relative_path != self.file.relative_path:
                raise ValueError("parsed diagnostic relative_path must match file")
            if diagnostic.parser_spec_version != self.file.parser_spec_version:
                raise ValueError("parsed diagnostic parser_spec_version must match file")


@dataclass(frozen=True)
class PendingCodeReference:
    pending_id: str
    repository_id: str
    reference_id: str
    source_revision: str
    relation_kind: str
    target_key: str
    reason: str
    parser_spec_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "pending_id",
            "repository_id",
            "reference_id",
            "source_revision",
            "relation_kind",
            "target_key",
            "reason",
            "parser_spec_version",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.relation_kind not in CODE_RELATION_KINDS:
            raise ValueError(f"unsupported relation_kind: {self.relation_kind}")


@dataclass(frozen=True)
class CodeManifest:
    generation_id: str
    schema_version: str
    parser_spec_version: str
    repository_ids: tuple[str, ...]
    policy_revision: str
    source_revisions: tuple[tuple[str, str], ...] = ()
    file_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_nested_tuple_attr(self, "source_revisions")
        _normalize_tuple_attr(self, "file_ids")
        for field_name in ("generation_id", "schema_version", "parser_spec_version", "policy_revision"):
            _require_non_empty(getattr(self, field_name), field_name)
        _require_tuple(self.repository_ids, "repository_ids")
        for repository_id in self.repository_ids:
            _require_non_empty(repository_id, "repository_ids")
        _require_tuple(self.source_revisions, "source_revisions")
        for source_revision in self.source_revisions:
            if len(source_revision) != 2:
                raise ValueError("source_revisions entries must contain repository_id and revision")
            repository_id, revision = source_revision
            _require_non_empty(repository_id, "source_revisions.repository_id")
            _require_non_empty(revision, "source_revisions.revision")
        _require_tuple(self.file_ids, "file_ids")
        for file_id in self.file_ids:
            _require_non_empty(file_id, "file_ids")


@dataclass(frozen=True)
class CodeReconcilePlan:
    manifest: CodeManifest
    files: tuple[CodeFileSnapshot, ...]
    symbols: tuple[CodeSymbolRecord, ...]
    edges: tuple[CodeEdgeRecord, ...]
    pending_references: tuple[PendingCodeReference, ...] = ()
    deleted_file_ids: tuple[str, ...] = ()
    run_id: str = ""

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "files")
        _normalize_tuple_attr(self, "symbols")
        _normalize_tuple_attr(self, "edges")
        _normalize_tuple_attr(self, "pending_references")
        _normalize_tuple_attr(self, "deleted_file_ids")
        if self.run_id:
            _require_non_empty(self.run_id, "run_id")
        repositories = set(self.manifest.repository_ids)
        for record in self.files:
            if record.repository_id not in repositories:
                raise ValueError("record repository_id is not present in manifest")
        for symbol in self.symbols:
            if symbol.repository_id not in repositories:
                raise ValueError("record repository_id is not present in manifest")
        for edge in self.edges:
            if edge.repository_id not in repositories:
                raise ValueError("record repository_id is not present in manifest")
        for pending in self.pending_references:
            if pending.repository_id not in repositories:
                raise ValueError("record repository_id is not present in manifest")
        for file_id in self.deleted_file_ids:
            _require_non_empty(file_id, "deleted_file_ids")


@dataclass(frozen=True)
class CodeApplyResult:
    generation_id: str
    repository_ids: tuple[str, ...]
    activated: bool
    file_count: int
    symbol_count: int
    edge_count: int
    pending_reference_count: int
    diagnostics: tuple[CodeParseDiagnostic, ...] = ()
    freshness: CodeFreshnessState = "fresh"
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION
    schema_version: str = CODE_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "diagnostics")
        _require_non_empty(self.generation_id, "generation_id")
        _require_bool(self.activated, "activated")
        _require_tuple(self.repository_ids, "repository_ids")
        _require_non_negative(self.file_count, "file_count")
        _require_non_negative(self.symbol_count, "symbol_count")
        _require_non_negative(self.edge_count, "edge_count")
        _require_non_negative(self.pending_reference_count, "pending_reference_count")
        _require_tuple(self.diagnostics, "diagnostics")
        _require_freshness(self.freshness)
        _require_non_empty(self.parser_spec_version, "parser_spec_version")
        _require_non_empty(self.schema_version, "schema_version")


@dataclass(frozen=True)
class CodeSymbolQuery:
    query_text: str
    repository_ids: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    path_prefix: str | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "kinds")
        _require_non_empty(self.query_text.strip(), "query_text")
        _require_tuple(self.repository_ids, "repository_ids")
        _require_tuple(self.kinds, "kinds")
        _require_positive(self.limit, "limit")
        for repository_id in self.repository_ids:
            _require_non_empty(repository_id, "repository_ids")
        for kind in self.kinds:
            if kind not in CODE_SYMBOL_KINDS:
                raise ValueError(f"unsupported symbol kind: {kind}")


@dataclass(frozen=True)
class CodeSymbolHit:
    symbol_id: str
    repository_id: str
    file_id: str
    relative_path: str
    kind: str
    language_kind: str
    name: str
    qualified_name: str
    signature: str | None
    start_line: int
    end_line: int
    score: float = 0.0
    content_hash: str | None = None
    source_revision: str | None = None
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "symbol_id",
            "repository_id",
            "file_id",
            "relative_path",
            "kind",
            "language_kind",
            "name",
            "qualified_name",
        ):
            _require_non_empty(getattr(self, field_name), field_name)
        if self.kind not in CODE_SYMBOL_KINDS:
            raise ValueError(f"unsupported symbol kind: {self.kind}")
        _require_relative_path(self.relative_path)
        _require_line_range(self.start_line, self.end_line)
        if self.content_hash is not None:
            _require_digest(self.content_hash, "content_hash")
        if self.source_revision is not None:
            _require_non_empty(self.source_revision, "source_revision")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")


@dataclass(frozen=True)
class CodeTraversalQuery:
    symbol_id: str
    repository_id: str | None = None
    direction: CodeTraversalDirection = "outbound"
    depth: int = 1
    limit: int = 100
    include_uncertain: bool = False

    def __post_init__(self) -> None:
        _require_bool(self.include_uncertain, "include_uncertain")
        _require_non_empty(self.symbol_id, "symbol_id")
        if self.repository_id is not None:
            _require_non_empty(self.repository_id, "repository_id")
        if self.direction not in ("inbound", "outbound"):
            raise ValueError(f"unsupported traversal direction: {self.direction}")
        _require_non_negative(self.depth, "depth")
        _require_positive(self.limit, "limit")


@dataclass(frozen=True)
class CodeTraversalResult:
    root_symbol_id: str
    direction: CodeTraversalDirection
    hits: tuple[CodeSymbolHit, ...]
    edges: tuple[CodeEdgeRecord, ...] = ()
    max_depth: int = 0
    warnings: tuple[str, ...] = ()
    freshness: CodeFreshnessState = "fresh"
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION
    schema_version: str = CODE_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "hits")
        _normalize_tuple_attr(self, "edges")
        _normalize_tuple_attr(self, "warnings")
        _require_non_empty(self.root_symbol_id, "root_symbol_id")
        if self.direction not in ("inbound", "outbound"):
            raise ValueError(f"unsupported traversal direction: {self.direction}")
        _require_tuple(self.hits, "hits")
        _require_tuple(self.edges, "edges")
        _require_non_negative(self.max_depth, "max_depth")
        _require_tuple(self.warnings, "warnings")
        _require_freshness(self.freshness)
        _require_non_empty(self.parser_spec_version, "parser_spec_version")
        _require_non_empty(self.schema_version, "schema_version")


@dataclass(frozen=True)
class CodeIndexRequest:
    repository_ids: tuple[str, ...] = ()
    full: bool = False
    dry_run: bool = False
    verify: bool = False

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _require_bool(self.full, "full")
        _require_bool(self.dry_run, "dry_run")
        _require_bool(self.verify, "verify")
        for repository_id in self.repository_ids:
            _require_non_empty(repository_id, "repository_ids")


@dataclass(frozen=True)
class CodeIndexPlan:
    request: CodeIndexRequest
    repository_ids: tuple[str, ...]
    changed_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]
    parser_spec_version: str
    schema_version: str = CODE_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "changed_paths")
        _normalize_tuple_attr(self, "deleted_paths")
        _validate_relative_paths(self.changed_paths, "changed_paths")
        _validate_relative_paths(self.deleted_paths, "deleted_paths")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")
        _require_non_empty(self.schema_version, "schema_version")


@dataclass(frozen=True)
class CodeRunReport:
    run_id: str
    mode: CodeIndexMode
    repository_ids: tuple[str, ...]
    status: CodeFreshnessState
    files_discovered: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    files_retried: int = 0
    symbols_extracted: int = 0
    edges_extracted: int = 0
    edges_resolved: int = 0
    edges_ambiguous: int = 0
    edges_unresolved: int = 0
    pending_paths: tuple[str, ...] = ()
    diagnostics: tuple[CodeParseDiagnostic, ...] = ()
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION
    schema_version: str = CODE_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "pending_paths")
        _normalize_tuple_attr(self, "diagnostics")
        _validate_relative_paths(self.pending_paths, "pending_paths")
        _require_non_empty(self.run_id, "run_id")
        if self.mode not in ("full", "incremental"):
            raise ValueError(f"unsupported index mode: {self.mode}")
        _require_tuple(self.repository_ids, "repository_ids")
        _require_freshness(self.status)
        for field_name in (
            "files_discovered",
            "files_parsed",
            "files_skipped",
            "files_deleted",
            "files_retried",
            "symbols_extracted",
            "edges_extracted",
            "edges_resolved",
            "edges_ambiguous",
            "edges_unresolved",
        ):
            _require_non_negative(getattr(self, field_name), field_name)
        _require_tuple(self.pending_paths, "pending_paths")
        _require_tuple(self.diagnostics, "diagnostics")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")
        _require_non_empty(self.schema_version, "schema_version")


@dataclass(frozen=True)
class CodeFreshnessRequest:
    repository_ids: tuple[str, ...] = ()
    verify: bool = False

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _require_bool(self.verify, "verify")
        for repository_id in self.repository_ids:
            _require_non_empty(repository_id, "repository_ids")


@dataclass(frozen=True)
class CodeFreshnessReport:
    repository_ids: tuple[str, ...]
    state: CodeFreshnessState
    warnings: tuple[str, ...] = ()
    pending_paths: tuple[str, ...] = ()
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION
    schema_version: str = CODE_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "warnings")
        _normalize_tuple_attr(self, "pending_paths")
        _validate_relative_paths(self.pending_paths, "pending_paths")
        _require_freshness(self.state)
        _require_tuple(self.warnings, "warnings")
        _require_tuple(self.pending_paths, "pending_paths")
        _require_non_empty(self.parser_spec_version, "parser_spec_version")
        _require_non_empty(self.schema_version, "schema_version")


# CLI/query records are kept here so adapters do not grow a second contract.
@dataclass(frozen=True)
class CodeSymbolSearchRequest:
    query_text: str
    repository_ids: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    path_prefix: str | None = None
    limit: int = 20
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repository_ids")
        _normalize_tuple_attr(self, "kinds")
        CodeSymbolQuery(self.query_text, self.repository_ids, self.kinds, self.path_prefix, self.limit)
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeSymbolRequest:
    symbol_id: str
    include_source: bool = False
    max_lines: int = 80
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_bool(self.include_source, "include_source")
        _require_non_empty(self.symbol_id, "symbol_id")
        _require_positive(self.max_lines, "max_lines")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeFileOutlineRequest:
    repository_id: str
    relative_path: str
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _require_relative_path(self.relative_path)
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeTraversalRequest:
    symbol_id: str
    depth: int = 1
    limit: int = 100
    output_format: CodeOutputFormat = "text"
    include_uncertain: bool = False

    def __post_init__(self) -> None:
        _require_bool(self.include_uncertain, "include_uncertain")
        CodeTraversalQuery(
            symbol_id=self.symbol_id,
            depth=self.depth,
            limit=self.limit,
            include_uncertain=self.include_uncertain,
        )
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeImpactRequest:
    symbol_id: str
    direction: CodeTraversalDirection = "inbound"
    depth: int = 3
    limit: int = 100
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        CodeTraversalQuery(symbol_id=self.symbol_id, direction=self.direction, depth=self.depth, limit=self.limit)
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeSearchResponse:
    query_text: str
    results: tuple[CodeSymbolHit, ...]
    freshness: CodeFreshnessState
    warnings: tuple[str, ...] = ()
    output_format: CodeOutputFormat = "text"
    candidate_count: int = 0

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "results")
        _normalize_tuple_attr(self, "warnings")
        _require_non_empty(self.query_text.strip(), "query_text")
        _require_tuple(self.results, "results")
        _require_freshness(self.freshness)
        _require_tuple(self.warnings, "warnings")
        _require_output_format(self.output_format)
        _require_non_negative(self.candidate_count, "candidate_count")


@dataclass(frozen=True)
class CodeSymbolResponse:
    symbol: CodeSymbolRecord | None
    freshness: CodeFreshnessState
    source_lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "source_lines")
        _normalize_tuple_attr(self, "warnings")
        _require_freshness(self.freshness)
        _require_tuple(self.source_lines, "source_lines")
        _require_tuple(self.warnings, "warnings")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeFileOutlineResponse:
    repository_id: str
    relative_path: str
    symbols: tuple[CodeSymbolRecord, ...]
    freshness: CodeFreshnessState
    warnings: tuple[str, ...] = ()
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "symbols")
        _normalize_tuple_attr(self, "warnings")
        _require_non_empty(self.repository_id, "repository_id")
        _require_relative_path(self.relative_path)
        _require_tuple(self.symbols, "symbols")
        _require_freshness(self.freshness)
        _require_tuple(self.warnings, "warnings")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeTraversalResponse:
    result: CodeTraversalResult
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeRepositoryAddRequest:
    repository_id: str
    root_path: Path
    display_name: str | None = None
    languages: tuple[str, ...] = ()
    include_globs: tuple[str, ...] = ()
    exclude_globs: tuple[str, ...] = ()
    watch: bool = False
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        if not isinstance(self.root_path, Path) or not str(self.root_path):
            raise ValueError("root_path is required")
        if self.display_name is not None:
            _require_non_empty(self.display_name, "display_name")
        _normalize_tuple_attr(self, "languages")
        _normalize_tuple_attr(self, "include_globs")
        _normalize_tuple_attr(self, "exclude_globs")
        for field_name, values in (
            ("languages", self.languages),
            ("include_globs", self.include_globs),
            ("exclude_globs", self.exclude_globs),
        ):
            for value in values:
                _require_non_empty(value, field_name)
        _require_bool(self.watch, "watch")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeRepositoryListRequest:
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeRepositoryRemoveRequest:
    repository_id: str
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeRepositoryListResponse:
    repositories: tuple[CodeRepositoryEntry, ...]
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _normalize_tuple_attr(self, "repositories")
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeIndexCliRequest:
    index: CodeIndexRequest = field(default_factory=CodeIndexRequest)
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeStatusRequest:
    freshness: CodeFreshnessRequest = field(default_factory=CodeFreshnessRequest)
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeIndexCliResponse:
    report: CodeRunReport
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeStatusResponse:
    report: CodeFreshnessReport
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_output_format(self.output_format)


@dataclass(frozen=True)
class CodeRepositoryMutationResponse:
    repository_id: str
    changed: bool
    warnings: tuple[str, ...] = ()
    output_format: CodeOutputFormat = "text"

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        _normalize_tuple_attr(self, "warnings")
        _require_bool(self.changed, "changed")
        _require_output_format(self.output_format)


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_digest(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    if len(value) != 64 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_relative_path(value: str) -> None:
    _require_non_empty(value, "relative_path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("relative_path must stay within the repository root")


def _validate_relative_paths(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} entries must be strings")
        try:
            _require_relative_path(value)
        except ValueError as error:
            raise ValueError(f"{field_name} contains an invalid relative path") from error


def _normalize_tuple_attr(instance: object, field_name: str) -> tuple[object, ...]:
    value = getattr(instance, field_name)
    if isinstance(value, list):
        value = tuple(value)
        object.__setattr__(instance, field_name, value)
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be an immutable tuple or list")
    return value


def _normalize_nested_tuple_attr(instance: object, field_name: str) -> tuple[tuple[object, ...], ...]:
    values = _normalize_tuple_attr(instance, field_name)
    normalized: tuple[tuple[object, ...], ...] = tuple(
        tuple(value) if isinstance(value, (tuple, list)) else _raise_nested_tuple(field_name) for value in values
    )
    object.__setattr__(instance, field_name, normalized)
    return normalized


def _raise_nested_tuple(field_name: str) -> tuple[object, ...]:
    raise ValueError(f"{field_name} entries must be immutable tuples or lists")


def _require_tuple(value: object, field_name: str) -> None:
    """Require an already-normalized immutable sequence for internal checks."""
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be an immutable tuple")


def _require_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")


def _require_non_negative(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_line(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a one-based source line")


def _require_line_range(start_line: int, end_line: int) -> None:
    _require_line(start_line, "start_line")
    _require_line(end_line, "end_line")
    if end_line < start_line:
        raise ValueError("line range is invalid")


def _require_optional_range(
    start_line: int | None,
    end_line: int | None,
    start_column: int | None,
    end_column: int | None,
) -> None:
    values = (start_line, end_line, start_column, end_column)
    if all(value is None for value in values):
        return
    if any(value is None for value in values):
        raise ValueError("diagnostic range must be complete")
    assert start_line is not None
    assert end_line is not None
    assert start_column is not None
    assert end_column is not None
    _require_line_range(start_line, end_line)
    _require_non_negative(start_column, "start_column")
    _require_non_negative(end_column, "end_column")


def _require_freshness(value: str) -> None:
    if value not in CODE_FRESHNESS_STATES:
        raise ValueError(f"unsupported freshness state: {value}")


def _require_output_format(value: str) -> None:
    if value not in ("text", "json"):
        raise ValueError(f"unsupported output format: {value}")


def _line_count(content: bytes) -> int:
    if not content:
        return 0
    return content.count(b"\n") + (0 if content.endswith(b"\n") else 1)


def code_file_identity(repository_id: str, relative_path: str) -> str:
    return hashlib.sha256(f"code-file-v1\0{repository_id}\0{relative_path}".encode()).hexdigest()
