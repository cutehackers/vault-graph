"""Read-only structural queries over the active code projection."""

from __future__ import annotations

from collections.abc import Iterable

from vault_graph.code_index.code_freshness import CodeFreshnessService
from vault_graph.code_index.code_models import (
    CodeFileOutlineRequest,
    CodeFileOutlineResponse,
    CodeFreshnessReport,
    CodeFreshnessRequest,
    CodeImpactRequest,
    CodeRepositoryEntry,
    CodeSearchResponse,
    CodeSymbolQuery,
    CodeSymbolRecord,
    CodeSymbolRequest,
    CodeSymbolResponse,
    CodeSymbolSearchRequest,
    CodeTraversalDirection,
    CodeTraversalQuery,
    CodeTraversalRequest,
    CodeTraversalResponse,
    code_file_identity,
)
from vault_graph.code_index.code_projection_service import CodeProjectionService
from vault_graph.code_index.repository_catalog import CodeRepositoryCatalog
from vault_graph.code_index.source_evidence_reader import SourceEvidenceReader
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore

MAX_QUERY_LIMIT = 100
MAX_TRAVERSAL_DEPTH = 8


class CodeQueryService:
    """Expose bounded code queries without exposing projection implementation details."""

    def __init__(
        self,
        *,
        catalog: CodeRepositoryCatalog | Iterable[CodeRepositoryEntry],
        store: CodeProjectionStore,
        freshness_service: CodeFreshnessService | CodeProjectionService,
        repository_ids: tuple[str, ...] = (),
    ) -> None:
        entries = catalog.entries() if hasattr(catalog, "entries") else tuple(catalog)
        self._entries = tuple(sorted(entries, key=lambda entry: entry.repository_id))
        self._entry_ids = {entry.repository_id for entry in self._entries}
        self._store = store
        self._freshness_service = freshness_service
        self._repository_ids = self._validate_scope(repository_ids)
        self._source_reader = SourceEvidenceReader(self._entries)

    def search_symbols(self, request: CodeSymbolSearchRequest) -> CodeSearchResponse:
        scope = self._scope(request.repository_ids)
        response = self._freshness(scope)
        hits = self._store.search_symbols(
            CodeSymbolQuery(
                request.query_text,
                scope,
                request.kinds,
                request.path_prefix,
                min(request.limit, MAX_QUERY_LIMIT),
            )
        )
        return CodeSearchResponse(
            query_text=request.query_text,
            results=tuple(
                sorted(
                    hits,
                    key=lambda item: (
                        item.score,
                        item.repository_id,
                        item.relative_path,
                        item.start_line,
                        item.symbol_id,
                    ),
                )
            ),
            freshness=response.state,
            warnings=self._redact_warnings(response.warnings),
            output_format=request.output_format,
            candidate_count=len(hits),
        )

    def get_symbol(self, request: CodeSymbolRequest) -> CodeSymbolResponse:
        symbol, warnings = self._resolve_symbol(request.symbol_id, request.repository_id, request.relative_path)
        freshness = self._freshness(self._scope((request.repository_id,) if request.repository_id else ()))
        source_uri = None
        source_lines: tuple[str, ...] = ()
        if symbol is not None and request.include_source:
            relative_path = self._relative_path(symbol)
            if relative_path is None:
                warnings = (*warnings, "source_unavailable")
            else:
                evidence = self._source_reader.read(symbol, relative_path=relative_path, max_lines=request.max_lines)
                source_uri = evidence.source_uri
                source_lines = evidence.lines
                warnings = (*warnings, *evidence.warnings)
        return CodeSymbolResponse(
            symbol=symbol,
            freshness=freshness.state,
            source_uri=source_uri,
            source_lines=source_lines,
            warnings=tuple(
                sorted(set((*self._redact_warnings(freshness.warnings), *warnings))),
            ),
            output_format=request.output_format,
        )

    def get_file_outline(self, request: CodeFileOutlineRequest) -> CodeFileOutlineResponse:
        freshness = self._freshness(self._scope((request.repository_id,)))
        symbols = tuple(
            sorted(
                (
                    symbol
                    for symbol in self._store.symbols((request.repository_id,))
                    if self._relative_path(symbol) == request.relative_path
                ),
                key=lambda symbol: (symbol.start_line, symbol.start_column, symbol.symbol_id),
            )
        )
        return CodeFileOutlineResponse(
            repository_id=request.repository_id,
            relative_path=request.relative_path,
            symbols=symbols,
            freshness=freshness.state,
            warnings=self._redact_warnings(freshness.warnings),
            output_format=request.output_format,
        )

    def get_callers(self, request: CodeTraversalRequest) -> CodeTraversalResponse:
        return self._traverse(request, direction="inbound")

    def get_callees(self, request: CodeTraversalRequest) -> CodeTraversalResponse:
        return self._traverse(request, direction="outbound")

    def get_impact(self, request: CodeImpactRequest) -> CodeTraversalResponse:
        traversal = CodeTraversalRequest(
            symbol_id=request.symbol_id,
            repository_id=request.repository_id,
            relative_path=request.relative_path,
            depth=request.depth,
            limit=request.limit,
            output_format=request.output_format,
            include_uncertain=request.include_uncertain,
        )
        return self._traverse(traversal, direction=request.direction)

    def _traverse(self, request: CodeTraversalRequest, *, direction: CodeTraversalDirection) -> CodeTraversalResponse:
        root, resolve_warnings = self._resolve_symbol(request.symbol_id, request.repository_id, request.relative_path)
        requested_scope = (
            (root.repository_id,) if root is not None else (request.repository_id,) if request.repository_id else ()
        )
        scope = self._scope(requested_scope)
        freshness = self._freshness(scope)
        if root is None:
            result = self._store.traverse(
                CodeTraversalQuery(symbol_id=request.symbol_id, direction=direction, depth=0, limit=1)
            )
        else:
            result = self._store.traverse(
                CodeTraversalQuery(
                    symbol_id=root.symbol_id,
                    repository_id=root.repository_id,
                    direction=direction,
                    depth=min(request.depth, MAX_TRAVERSAL_DEPTH),
                    limit=min(request.limit, MAX_QUERY_LIMIT),
                    include_uncertain=request.include_uncertain,
                    relation_kinds=("CALLS",) if direction in {"inbound", "outbound"} else (),
                )
            )
        from dataclasses import replace

        return CodeTraversalResponse(
            result=replace(
                result,
                freshness=freshness.state,
                warnings=tuple(
                    sorted(set((*result.warnings, *self._redact_warnings(freshness.warnings), *resolve_warnings)))
                ),
            ),
            output_format=request.output_format,
        )

    def _resolve_symbol(
        self, symbol_or_id: str, repository_id: str | None, relative_path: str | None
    ) -> tuple[CodeSymbolRecord | None, tuple[str, ...]]:
        direct = self._store.get_symbol(symbol_or_id)
        if direct is not None:
            if self._matches(direct, repository_id, relative_path):
                return direct, ()
            return None, ("symbol_scope_mismatch",)
        scope = self._scope((repository_id,) if repository_id else ())
        matches = tuple(
            symbol
            for symbol in self._store.symbols(scope)
            if symbol_or_id in {symbol.name, symbol.qualified_name}
            and self._matches(symbol, repository_id, relative_path)
        )
        if len(matches) > 1:
            return None, ("ambiguous_symbol",)
        if not matches:
            return None, ("symbol_not_found",)
        return matches[0], ()

    def _matches(self, symbol: CodeSymbolRecord, repository_id: str | None, relative_path: str | None) -> bool:
        return (repository_id is None or symbol.repository_id == repository_id) and (
            relative_path is None or self._relative_path(symbol) == relative_path
        )

    def _relative_path(self, symbol: CodeSymbolRecord) -> str | None:
        for snapshot in self._store.file_snapshots((symbol.repository_id,)):
            if code_file_identity(symbol.repository_id, snapshot.relative_path) == symbol.file_id:
                return snapshot.relative_path
        return None

    def _scope(self, requested: tuple[str, ...]) -> tuple[str, ...]:
        scope = self._validate_scope(requested or self._repository_ids)
        if self._repository_ids and not set(scope).issubset(self._repository_ids):
            raise ValueError("repository_id is outside the query service scope")
        return scope

    def _validate_scope(self, repository_ids: tuple[str, ...]) -> tuple[str, ...]:
        invalid = set(repository_ids) - self._entry_ids
        if invalid:
            raise ValueError(f"unknown repository_id: {sorted(invalid)[0]}")
        return tuple(sorted(set(repository_ids)))

    def _freshness(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
        if isinstance(self._freshness_service, CodeFreshnessService):
            return self._freshness_service.compare(CodeFreshnessRequest(repository_ids=repository_ids))
        return self._freshness_service.status(repository_ids)

    def _redact_warnings(self, warnings: tuple[str, ...]) -> tuple[str, ...]:
        redacted: list[str] = []
        for warning in warnings:
            value = warning
            for entry in self._entries:
                value = value.replace(str(entry.root_path), "<repository-root>")
            redacted.append(value)
        return tuple(redacted)


__all__ = ["CodeQueryService", "MAX_QUERY_LIMIT", "MAX_TRAVERSAL_DEPTH"]
