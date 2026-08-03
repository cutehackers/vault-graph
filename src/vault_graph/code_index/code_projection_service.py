"""Application boundary for staged full and incremental code projections."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Literal

from vault_graph.code_index.code_freshness import CodeFreshnessService
from vault_graph.code_index.code_generation import CodeGenerationLayout, CodeProjectionGenerationManager
from vault_graph.code_index.code_models import (
    CODE_PROJECTION_SCHEMA_VERSION,
    CodeEdgeRecord,
    CodeFileInput,
    CodeFileSnapshot,
    CodeFreshnessReport,
    CodeFreshnessRequest,
    CodeFreshnessState,
    CodeIndexPlan,
    CodeIndexRequest,
    CodeManifest,
    CodeParseDiagnostic,
    CodeParseResult,
    CodeReconcilePlan,
    CodeRepositoryEntry,
    CodeRunReport,
    PendingCodeReference,
    code_file_identity,
)
from vault_graph.code_index.dart_parser import DartCodeParserAdapter
from vault_graph.code_index.parser_adapter import CodeParserAdapter
from vault_graph.code_index.python_parser import PythonCodeParserAdapter
from vault_graph.code_index.reference_resolution import CodeReferenceResolver
from vault_graph.code_index.repository_catalog import CodeRepositoryCatalog, repository_policy_revision
from vault_graph.code_index.source_scanning import CodeScanResult, CodeSourceScanner
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore
from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

StoreFactory = Callable[[Path, str], CodeProjectionStore]


class CodeProjectionService:
    """Build a complete desired snapshot, then atomically activate code state."""

    def __init__(
        self,
        *,
        catalog: CodeRepositoryCatalog | Iterable[CodeRepositoryEntry],
        scanner: CodeSourceScanner | None = None,
        parsers: Mapping[str, CodeParserAdapter] | None = None,
        resolver: CodeReferenceResolver | None = None,
        generation_manager: CodeProjectionGenerationManager,
        store_factory: StoreFactory | None = None,
    ) -> None:
        self._entries = _entries_from_catalog(catalog)
        self._scanner = scanner or CodeSourceScanner()
        self._parsers: dict[str, CodeParserAdapter] = dict(
            parsers or {"python": PythonCodeParserAdapter(), "dart": DartCodeParserAdapter()}
        )
        self._resolver = resolver or CodeReferenceResolver()
        self.generation_manager = generation_manager
        self._store_factory = store_factory or _sqlite_store
        self._parsed: dict[str, CodeParseResult] = {}
        self._snapshots: dict[str, CodeFileInput | CodeFileSnapshot] = {}
        self._pending: tuple[PendingCodeReference, ...] = ()
        self._syncing = False
        self.fail_next_apply = False

    @classmethod
    def for_testing(
        cls,
        *,
        state_path: Path,
        entries: Iterable[CodeRepositoryEntry],
        parsers: Mapping[str, CodeParserAdapter] | None = None,
    ) -> CodeProjectionService:
        return cls(
            catalog=tuple(entries),
            parsers=parsers,
            generation_manager=CodeProjectionGenerationManager(state_path),
        )

    def plan(self, request: CodeIndexRequest) -> CodeIndexPlan:
        if not isinstance(request, CodeIndexRequest):
            raise TypeError("request must be a CodeIndexRequest")
        entries = _select_entries(self._entries, request.repository_ids)
        scans = self._scan(entries)
        current = {
            code_file_identity(file.repository_id, file.relative_path): file for scan in scans for file in scan.files
        }
        current_ids = set(current)
        changed = tuple(
            file.relative_path
            for file_id, file in sorted(current.items())
            if request.full
            or file_id not in self._snapshots
            or self._snapshots[file_id].content_hash != file.content_hash
        )
        deleted = tuple(
            snapshot.relative_path
            for file_id, snapshot in sorted(self._snapshots.items())
            if file_id not in current_ids
        )
        return CodeIndexPlan(
            request=request,
            repository_ids=tuple(entry.repository_id for entry in entries),
            changed_paths=tuple(sorted(changed)),
            deleted_paths=tuple(sorted(deleted)),
            parser_spec_version=self._scanner.parser_spec_version,
        )

    def apply(self, request: CodeIndexRequest) -> CodeRunReport:
        if not isinstance(request, CodeIndexRequest):
            raise TypeError("request must be a CodeIndexRequest")
        requested_entries = _select_entries(self._entries, request.repository_ids)
        repository_ids = tuple(entry.repository_id for entry in requested_entries)
        mode: Literal["full", "incremental"] = "full" if request.full else "incremental"
        run_id = f"code-run-{uuid.uuid4().hex}"
        if request.dry_run:
            planned = self.plan(request)
            return CodeRunReport(
                run_id=run_id,
                mode=mode,
                repository_ids=repository_ids,
                status="stale",
                files_discovered=len(planned.changed_paths) + len(planned.deleted_paths),
                files_deleted=len(planned.deleted_paths),
                parser_spec_version=self._scanner.parser_spec_version,
            )
        self._syncing = True
        staged = None
        diagnostics: list[CodeParseDiagnostic] = []
        try:
            # A scoped run scans only the requested repositories. When an
            # active generation exists, its SQLite file is cloned into the
            # staged generation so untouched namespaces remain byte-for-byte
            # represented without re-reading their source files.
            scans = self._scan(requested_entries)
            files = tuple(file for scan in scans for file in scan.files)
            current_by_id = {code_file_identity(file.repository_id, file.relative_path): file for file in files}
            active = self.generation_manager.active_layout(())
            active_store = self._open_active_store(active)
            active_manifest = active_store.current_manifest(()) if active_store is not None else None
            existing_selected = self._existing_snapshots(active_store, repository_ids)
            old_ids = set(existing_selected)
            deleted_ids = old_ids - set(current_by_id)
            deleted_count = len(deleted_ids)
            parsed_results, parsed_count, skipped_count, parse_diagnostics = self._parse(files, full=request.full)
            diagnostics.extend(parse_diagnostics)
            all_files = tuple(result.file for result in parsed_results)
            untouched_files = (
                tuple(
                    snapshot
                    for snapshot in active_store.file_snapshots(active_manifest.repository_ids)
                    if snapshot.repository_id not in set(repository_ids)
                )
                if active_store is not None and active_manifest is not None
                else tuple(
                    _as_snapshot(snapshot)
                    for file_id, snapshot in self._snapshots.items()
                    if snapshot.repository_id not in set(repository_ids)
                )
            )
            untouched_symbols = (
                active_store.symbols(active_manifest.repository_ids)
                if active_store is not None and active_manifest is not None
                else tuple(
                    symbol
                    for result in self._parsed.values()
                    for symbol in result.symbols
                    if symbol.repository_id not in set(repository_ids)
                )
            )
            all_symbols = tuple(symbol for result in parsed_results for symbol in result.symbols) + tuple(
                symbol for symbol in untouched_symbols if symbol.repository_id not in set(repository_ids)
            )
            all_references = tuple(reference for result in parsed_results for reference in result.references)
            previous_pending = (
                tuple(
                    pending
                    for pending in active_store.pending_references(active_manifest.repository_ids)
                    if pending.repository_id in set(repository_ids)
                )
                if active_store is not None and active_manifest is not None
                else tuple(pending for pending in self._pending if pending.repository_id in set(repository_ids))
            )
            changed_ids = tuple(
                file_id
                for file_id, file in current_by_id.items()
                if request.full
                or file_id not in existing_selected
                or existing_selected[file_id].content_hash != file.content_hash
            )
            resolution = self._resolver.resolve(
                files=tuple(all_files) + tuple(untouched_files),
                symbols=all_symbols,
                references=all_references,
                previous_pending=() if request.full else previous_pending,
                changed_file_ids=None if request.full else tuple(changed_ids) + tuple(deleted_ids),
            )
            generation_ids = _generation_repository_ids(
                active_manifest.repository_ids if active_manifest is not None else (),
                self._entries,
                repository_ids,
            )
            generation_entries = tuple(entry for entry in self._entries if entry.repository_id in set(generation_ids))
            policy_revision = _policy_revision(generation_entries)
            staged = self.generation_manager.stage(generation_ids)
            if active is not None and active.database_path.exists():
                shutil.copy2(active.database_path, staged.database_path)
            store = self._store_factory(staged.database_path, policy_revision)
            source_revisions = dict(active_manifest.source_revisions) if active_manifest is not None else {}
            source_revisions.update((scan.repository_id, scan.source_revision) for scan in scans)
            if set(source_revisions) != set(generation_ids):
                raise RuntimeError("scoped code projection cannot establish untouched source revisions")
            active_file_ids = set(active_manifest.file_ids) if active_manifest is not None else set()
            desired_file_ids = (active_file_ids - deleted_ids) | set(current_by_id)
            manifest = CodeManifest(
                generation_id=staged.generation_id,
                schema_version=CODE_PROJECTION_SCHEMA_VERSION,
                parser_spec_version=self._scanner.parser_spec_version,
                repository_ids=generation_ids,
                policy_revision=policy_revision,
                source_revisions=tuple(sorted(source_revisions.items())),
                file_ids=tuple(sorted(desired_file_ids)),
            )
            reconcile = CodeReconcilePlan(
                manifest=manifest,
                files=tuple(sorted(all_files, key=lambda item: (item.repository_id, item.relative_path))),
                symbols=tuple(
                    sorted(
                        tuple(symbol for symbol in all_symbols if symbol.repository_id in set(repository_ids)),
                        key=lambda item: (item.repository_id, item.file_id, item.start_line, item.symbol_id),
                    )
                ),
                edges=tuple(edge for edge in resolution.edges if edge.repository_id in set(repository_ids)),
                pending_references=resolution.pending_references,
                deleted_file_ids=tuple(sorted(deleted_ids)),
                run_id=run_id,
            )
            if self.fail_next_apply:
                self.fail_next_apply = False
                raise RuntimeError("simulated code projection failure")
            store.apply_reconcile_plan(reconcile)
            health = store.health()
            if not health.schema_compatible:
                raise RuntimeError(f"staged code projection failed health audit: {health.message}")
            if request.verify and store.current_manifest(generation_ids) != manifest:
                raise RuntimeError("staged code projection manifest verification failed")
            warnings = tuple(sorted({warning for scan in scans for warning in scan.warnings}))
            diagnostics.extend(diagnostic for result in parsed_results for diagnostic in result.diagnostics)
            partial = bool(warnings or diagnostics)
            if hasattr(store, "record_freshness"):
                store.record_freshness(
                    "partial" if partial else "fresh", (*warnings, *(diagnostic.message for diagnostic in diagnostics))
                )
            self.generation_manager.activate(staged)
            self._parsed = {
                code_file_identity(result.file.repository_id, result.file.relative_path): result
                for result in parsed_results
            }
            retained_snapshots = {
                file_id: snapshot
                for file_id, snapshot in (
                    existing_selected.items() if active_store is not None else self._snapshots.items()
                )
                if file_id not in deleted_ids and snapshot.repository_id not in set(repository_ids)
            }
            self._snapshots = {**retained_snapshots, **current_by_id}
            retained_pending = tuple(
                pending
                for pending in (
                    active_store.pending_references(active_manifest.repository_ids)
                    if active_store is not None and active_manifest is not None
                    else self._pending
                )
                if pending.repository_id not in set(repository_ids)
            )
            self._pending = tuple((*retained_pending, *resolution.pending_references))
            return _run_report(
                run_id=run_id,
                mode=mode,
                repository_ids=repository_ids,
                status="partial" if partial else "fresh",
                files_discovered=len(files),
                files_parsed=parsed_count,
                files_skipped=skipped_count,
                files_deleted=deleted_count,
                files_retried=len(resolution.retried_reference_ids),
                symbols_extracted=sum(1 for symbol in all_symbols if symbol.repository_id in set(repository_ids)),
                edges=tuple(edge for edge in resolution.edges if edge.repository_id in set(repository_ids)),
                pending_paths=resolution.pending_references,
                files_by_id=current_by_id,
                diagnostics=tuple(diagnostics),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            if staged is not None:
                try:
                    self.generation_manager.discard(staged)
                except Exception:
                    pass
            self._record_active_failure(repository_ids, str(exc))
            return CodeRunReport(
                run_id=run_id,
                mode=mode,
                repository_ids=repository_ids,
                status="partial",
                diagnostics=tuple(diagnostics),
                pending_paths=(),
                parser_spec_version=self._scanner.parser_spec_version,
            )
        finally:
            self._syncing = False

    def status(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
        entries = _select_entries(self._entries, repository_ids)
        freshness = CodeFreshnessService(
            catalog=self._entries,
            scanner=self._scanner,
            generation_manager=self.generation_manager,
            parser_spec_version=self._scanner.parser_spec_version,
        )
        report = freshness.compare(CodeFreshnessRequest(repository_ids=tuple(entry.repository_id for entry in entries)))
        if self._syncing:
            from dataclasses import replace

            return replace(report, state="syncing", warnings=(*report.warnings, "code projection is syncing"))
        return report

    def _scan(self, entries: tuple[CodeRepositoryEntry, ...]) -> tuple[CodeScanResult, ...]:
        return tuple(self._scanner.scan(entry) for entry in entries)

    def _open_active_store(self, active: CodeGenerationLayout | None) -> SQLiteCodeProjectionStore | None:
        if active is None or not active.database_path.exists():
            return None
        store = SQLiteCodeProjectionStore.open_read_only(
            active.database_path,
            parser_spec_version=self._scanner.parser_spec_version,
        )
        health = store.health()
        if not health.schema_compatible:
            raise RuntimeError(f"active code projection is incompatible: {health.message}")
        return store

    def _record_active_failure(self, repository_ids: tuple[str, ...], message: str) -> None:
        """Persist a partial marker without changing the active generation."""

        try:
            active = self.generation_manager.active_layout(())
            if active is None or not active.database_path.exists():
                return
            reader = SQLiteCodeProjectionStore.open_read_only(
                active.database_path,
                parser_spec_version=self._scanner.parser_spec_version,
            )
            if not reader.health().schema_compatible:
                return
            writer = SQLiteCodeProjectionStore.open_writable(
                active.database_path,
                parser_spec_version=self._scanner.parser_spec_version,
            )
            writer.record_freshness(
                "partial",
                (f"code projection run failed for {','.join(repository_ids) or 'all repositories'}: {message}",),
            )
        except (OSError, RuntimeError, ValueError):
            # The old generation remains queryable even when its diagnostic
            # marker cannot be written (for example, a read-only state path).
            return

    def _existing_snapshots(
        self,
        active_store: SQLiteCodeProjectionStore | None,
        repository_ids: tuple[str, ...],
    ) -> dict[str, CodeFileInput | CodeFileSnapshot]:
        if active_store is not None:
            return {
                code_file_identity(snapshot.repository_id, snapshot.relative_path): snapshot
                for snapshot in active_store.file_snapshots(repository_ids)
            }
        return {
            file_id: snapshot
            for file_id, snapshot in self._snapshots.items()
            if snapshot.repository_id in set(repository_ids)
        }

    def _parse(
        self,
        files: tuple[CodeFileInput, ...],
        *,
        full: bool,
    ) -> tuple[tuple[CodeParseResult, ...], int, int, tuple[CodeParseDiagnostic, ...]]:
        results: list[CodeParseResult] = []
        diagnostics: list[CodeParseDiagnostic] = []
        parsed_count = 0
        skipped_count = 0
        for file in sorted(files, key=lambda item: (item.repository_id, item.relative_path)):
            file_id = code_file_identity(file.repository_id, file.relative_path)
            previous = self._parsed.get(file_id)
            if not full and previous is not None and previous.file.content_hash == file.content_hash:
                # Rebind the source revision while preserving the deterministic
                # AST records for an unchanged untracked file.
                results.append(_rebind_parse_result(previous, file))
                skipped_count += 1
                continue
            parser = self._parsers.get(file.language)
            if parser is None:
                skipped_count += 1
                continue
            try:
                results.append(parser.parse(file))
                parsed_count += 1
            except Exception as exc:
                diagnostic = CodeParseDiagnostic(
                    diagnostic_id=f"code-parse-{hashlib.sha256(f'{file.repository_id}:{file.relative_path}'.encode()).hexdigest()}",
                    repository_id=file.repository_id,
                    relative_path=file.relative_path,
                    severity="error",
                    code="parser_failed",
                    message=str(exc),
                    start_line=None,
                    start_column=None,
                    end_line=None,
                    end_column=None,
                    parser_spec_version=file.parser_spec_version,
                )
                diagnostics.append(diagnostic)
                results.append(
                    CodeParseResult(file=file.snapshot(), symbols=(), references=(), diagnostics=(diagnostic,))
                )
        self._parsed = {
            file_id: result
            for file_id, result in (
                (code_file_identity(item.file.repository_id, item.file.relative_path), item) for item in results
            )
        }
        return tuple(results), parsed_count, skipped_count, tuple(diagnostics)


def _entries_from_catalog(
    catalog: CodeRepositoryCatalog | Iterable[CodeRepositoryEntry],
) -> tuple[CodeRepositoryEntry, ...]:
    values = catalog.entries() if hasattr(catalog, "entries") else tuple(catalog)
    return tuple(sorted((entry for entry in values if entry.enabled), key=lambda item: item.repository_id))


def _select_entries(
    entries: tuple[CodeRepositoryEntry, ...], repository_ids: tuple[str, ...]
) -> tuple[CodeRepositoryEntry, ...]:
    if not repository_ids:
        return entries
    requested = set(repository_ids)
    unknown = requested - {entry.repository_id for entry in entries}
    if unknown:
        raise ValueError(f"unknown code repository: {sorted(unknown)[0]}")
    return tuple(entry for entry in entries if entry.repository_id in requested)


def _policy_revision(entries: tuple[CodeRepositoryEntry, ...]) -> str:
    payload = [(entry.repository_id, repository_policy_revision(entry)) for entry in entries]
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"code-policy-set-v1:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _generation_repository_ids(
    active_ids: tuple[str, ...],
    entries: tuple[CodeRepositoryEntry, ...],
    requested_ids: tuple[str, ...],
) -> tuple[str, ...]:
    # Bootstrap runs with no active generation create only the explicitly
    # requested namespace; later scoped runs clone and retain every active
    # registered namespace.
    registered = {entry.repository_id for entry in entries}
    retained = set(active_ids) & registered
    retained.update(requested_ids)
    return tuple(sorted(retained))


def _as_snapshot(value: CodeFileInput | CodeFileSnapshot) -> CodeFileSnapshot:
    return value.snapshot() if isinstance(value, CodeFileInput) else value


def _sqlite_store(database_path: Path, policy_revision: str) -> CodeProjectionStore:
    return SQLiteCodeProjectionStore.open_writable(database_path, policy_revision=policy_revision)


def _rebind_parse_result(previous: CodeParseResult, file: CodeFileInput) -> CodeParseResult:
    # A source revision is part of every evidence record. Re-parse is avoided
    # only when content is byte-identical; records are therefore safely rebound.
    from dataclasses import replace

    return CodeParseResult(
        file=file.snapshot(),
        symbols=tuple(
            replace(symbol, content_hash=file.content_hash, source_revision=file.source_revision)
            for symbol in previous.symbols
        ),
        references=tuple(
            replace(reference, parser_spec_version=file.parser_spec_version) for reference in previous.references
        ),
        diagnostics=tuple(
            replace(diagnostic, parser_spec_version=file.parser_spec_version) for diagnostic in previous.diagnostics
        ),
    )


def _run_report(
    *,
    run_id: str,
    mode: Literal["full", "incremental"],
    repository_ids: tuple[str, ...],
    status: CodeFreshnessState,
    files_discovered: int,
    files_parsed: int,
    files_skipped: int,
    files_deleted: int,
    files_retried: int,
    symbols_extracted: int,
    edges: tuple[CodeEdgeRecord, ...],
    pending_paths: tuple[PendingCodeReference, ...],
    files_by_id: dict[str, CodeFileInput],
    diagnostics: tuple[CodeParseDiagnostic, ...],
) -> CodeRunReport:
    statuses = [edge.extraction_status for edge in edges]
    pending_file_paths = tuple(
        sorted(
            {
                files_by_id[pending.source_file_id].relative_path
                for pending in pending_paths
                if pending.source_file_id in files_by_id
            }
        )
    )
    return CodeRunReport(
        run_id=run_id,
        mode=mode,
        repository_ids=repository_ids,
        status=status,
        files_discovered=files_discovered,
        files_parsed=files_parsed,
        files_skipped=files_skipped,
        files_deleted=files_deleted,
        files_retried=files_retried,
        symbols_extracted=symbols_extracted,
        edges_extracted=len(edges),
        edges_resolved=sum(status in {"extracted", "inferred"} for status in statuses),
        edges_ambiguous=statuses.count("ambiguous"),
        edges_unresolved=statuses.count("unresolved"),
        pending_paths=pending_file_paths,
        diagnostics=diagnostics,
    )


__all__ = ["CodeProjectionService"]
