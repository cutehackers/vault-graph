"""Freshness comparison for the live source tree and active code generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

from vault_graph.code_index.code_generation import CodeGenerationLayout, CodeProjectionGenerationManager
from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CODE_PROJECTION_SCHEMA_VERSION,
    CodeFreshnessReport,
    CodeFreshnessRequest,
    CodeFreshnessState,
    CodeRepositoryEntry,
)
from vault_graph.code_index.repository_catalog import CodeRepositoryCatalog, repository_policy_revision
from vault_graph.code_index.source_scanning import CodeScanResult, CodeSourceScanner
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore
from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

StoreFactory = Callable[[Path, str], CodeProjectionStore]


class CodeFreshnessService:
    """Compare current repository fingerprints with a code generation manifest."""

    def __init__(
        self,
        *,
        catalog: CodeRepositoryCatalog | Iterable[CodeRepositoryEntry],
        scanner: CodeSourceScanner | None = None,
        generation_manager: CodeProjectionGenerationManager | None = None,
        store: CodeProjectionStore | None = None,
        store_factory: StoreFactory | None = None,
        parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
    ) -> None:
        self._entries = _entries_from_catalog(catalog)
        self._scanner = scanner or CodeSourceScanner(parser_spec_version=parser_spec_version)
        self._generation_manager = generation_manager
        self._store = store
        self._store_factory = store_factory
        self._parser_spec_version = parser_spec_version
        self._last_report: CodeFreshnessReport | None = None

    def compare(self, request: CodeFreshnessRequest) -> CodeFreshnessReport:
        if not isinstance(request, CodeFreshnessRequest):
            raise TypeError("request must be a CodeFreshnessRequest")
        entries = _select_entries(self._entries, request.repository_ids)
        repository_ids = tuple(entry.repository_id for entry in entries)
        warnings: list[str] = []
        pending_paths: list[str] = []
        if not entries:
            report = CodeFreshnessReport(
                repository_ids=(),
                state="unknown",
                warnings=("no enabled code repositories are registered",),
                parser_spec_version=self._parser_spec_version,
            )
            self._last_report = report
            return report

        scans: list[CodeScanResult] = []
        for entry in entries:
            try:
                scans.append(self._scanner.scan(entry))
            except (OSError, ValueError) as exc:
                warnings.append(f"source unavailable for {entry.repository_id}: {exc}")
        if len(scans) != len(entries):
            report = CodeFreshnessReport(
                repository_ids=repository_ids,
                state="unknown",
                warnings=tuple(sorted(set(warnings))),
                parser_spec_version=self._parser_spec_version,
            )
            self._last_report = report
            return report
        for scan in scans:
            warnings.extend(scan.warnings)

        layout = self._active_layout(repository_ids)
        if layout is None and self._store is None:
            report = CodeFreshnessReport(
                repository_ids=repository_ids,
                state="unavailable",
                warnings=tuple(sorted(set((*warnings, "no compatible active code generation")))),
                parser_spec_version=self._parser_spec_version,
            )
            self._last_report = report
            return report

        generation_entries = (
            tuple(entry for entry in self._entries if entry.repository_id in set(layout.repository_ids))
            if layout is not None
            else entries
        )
        expected_policy = _policy_revision(generation_entries)
        if self._store is not None:
            projection = self._store
        else:
            assert layout is not None
            projection = self._open_store(layout.database_path, expected_policy)
        try:
            health = projection.health()
        except Exception as exc:  # backend failures are represented as availability state
            health = None
            warnings.append(f"code projection unavailable: {exc}")
        if health is None or not health.schema_compatible:
            if health is not None:
                warnings.append(f"code projection unavailable: {health.message}")
            report = CodeFreshnessReport(
                repository_ids=repository_ids,
                state="unavailable",
                warnings=tuple(sorted(set(warnings))),
                parser_spec_version=self._parser_spec_version,
            )
            self._last_report = report
            return report

        manifest = projection.current_manifest(repository_ids)
        manifest_revisions = dict(manifest.source_revisions)
        current_revisions = {scan.repository_id: scan.source_revision for scan in scans}
        if manifest.parser_spec_version != self._parser_spec_version:
            warnings.append("parser specification differs from active generation")
        if manifest.schema_version != CODE_PROJECTION_SCHEMA_VERSION:
            warnings.append("code projection schema differs from active generation")
        if manifest.policy_revision != expected_policy:
            warnings.append("repository scan policy differs from active generation")
        for repository_id, current_revision in current_revisions.items():
            indexed_revision = manifest_revisions.get(repository_id)
            if indexed_revision != current_revision:
                warnings.append(f"source revision changed: {repository_id}")

        file_method = getattr(projection, "file_snapshots", None)
        indexed_files = (
            {(snapshot.repository_id, snapshot.relative_path): snapshot for snapshot in file_method(repository_ids)}
            if callable(file_method)
            else {}
        )
        current_files = {
            (file.repository_id, file.relative_path): file.snapshot() for scan in scans for file in scan.files
        }
        if not callable(file_method):
            warnings.append("content verification is unavailable for this store")
        elif indexed_files.keys() != current_files.keys():
            warnings.append("indexed file scope differs from source scan")
        for key in indexed_files.keys() & current_files.keys():
            indexed = indexed_files[key]
            current = current_files[key]
            if indexed.content_hash != current.content_hash:
                warnings.append(f"content hash changed: {key[0]}/{key[1]}")
            if request.verify and (
                indexed.language != current.language
                or indexed.byte_count != current.byte_count
                or indexed.line_count != current.line_count
                or indexed.parser_spec_version != current.parser_spec_version
            ):
                warnings.append(f"file fingerprint metadata changed: {key[0]}/{key[1]}")

        last_state, last_warnings = _last_freshness(projection)
        if last_state == "partial":
            warnings.extend(last_warnings)
            warnings.append("last code projection run was partial")

        pending_paths.extend(_pending_paths(projection, repository_ids))
        if pending_paths:
            warnings.append("unresolved references remain pending")

        state: CodeFreshnessState = "fresh" if not warnings else "stale"
        if last_state == "partial":
            state = "partial"
        if any(message.startswith("source_unavailable:") for message in warnings):
            state = "unknown"
        report = CodeFreshnessReport(
            repository_ids=repository_ids,
            state=state,
            warnings=tuple(sorted(set(warnings))),
            pending_paths=tuple(sorted(set(pending_paths))),
            parser_spec_version=self._parser_spec_version,
        )
        self._last_report = report
        return report

    def read_status(self, request: CodeFreshnessRequest) -> CodeFreshnessReport:
        """Read bounded persisted projection status without scanning source files."""

        if not isinstance(request, CodeFreshnessRequest):
            raise TypeError("request must be a CodeFreshnessRequest")
        entries = _select_entries(self._entries, request.repository_ids)
        repository_ids = tuple(entry.repository_id for entry in entries)
        if not entries:
            return self._remember(
                CodeFreshnessReport(
                    repository_ids=(),
                    state="unknown",
                    warnings=("no enabled code repositories are registered",),
                    parser_spec_version=self._parser_spec_version,
                )
            )
        layout = self._active_layout(repository_ids)
        if layout is None and self._store is None:
            return self._remember(
                CodeFreshnessReport(
                    repository_ids=repository_ids,
                    state="unavailable",
                    warnings=("no compatible active code generation",),
                    parser_spec_version=self._parser_spec_version,
                )
            )
        generation_entries = (
            tuple(entry for entry in self._entries if entry.repository_id in set(layout.repository_ids))
            if layout is not None
            else entries
        )
        if self._store is not None:
            projection = self._store
        else:
            assert layout is not None
            projection = self._open_store(layout.database_path, _policy_revision(generation_entries))
        try:
            health = projection.health()
        except Exception as exc:
            return self._remember(
                CodeFreshnessReport(
                    repository_ids=repository_ids,
                    state="unavailable",
                    warnings=(f"code projection unavailable: {exc}",),
                    parser_spec_version=self._parser_spec_version,
                )
            )
        if not health.schema_compatible:
            return self._remember(
                CodeFreshnessReport(
                    repository_ids=repository_ids,
                    state="unavailable",
                    warnings=(f"code projection unavailable: {health.message}",),
                    parser_spec_version=self._parser_spec_version,
                )
            )
        warnings = ["live source verification was not requested"]
        manifest = projection.current_manifest(repository_ids)
        if manifest.parser_spec_version != self._parser_spec_version:
            warnings.append("parser specification differs from active generation")
        if manifest.schema_version != CODE_PROJECTION_SCHEMA_VERSION:
            warnings.append("code projection schema differs from active generation")
        if manifest.policy_revision != _policy_revision(generation_entries):
            warnings.append("repository scan policy differs from active generation")
        pending_paths = _pending_paths(projection, repository_ids)
        if pending_paths:
            warnings.append("unresolved references remain pending")
        last_state, last_warnings = _last_freshness(projection)
        warnings.extend(last_warnings)
        state: CodeFreshnessState = (
            cast(CodeFreshnessState, last_state)
            if last_state in {"partial", "syncing", "unavailable", "stale"}
            else "unknown"
        )
        return self._remember(
            CodeFreshnessReport(
                repository_ids=repository_ids,
                state=state,
                warnings=tuple(sorted(set(warnings))),
                pending_paths=tuple(sorted(set(pending_paths))),
                parser_spec_version=self._parser_spec_version,
            )
        )

    def read_status_for(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
        """Read persisted status for a repository scope without a live scan."""

        return self.read_status(CodeFreshnessRequest(repository_ids=repository_ids))

    def _remember(self, report: CodeFreshnessReport) -> CodeFreshnessReport:
        self._last_report = report
        return report

    def _active_layout(self, repository_ids: tuple[str, ...]) -> CodeGenerationLayout | None:
        if self._generation_manager is None:
            return None
        try:
            return self._generation_manager.active_layout(repository_ids)
        except Exception:
            return None

    def _open_store(self, database_path: Path, policy_revision: str) -> CodeProjectionStore:
        if self._store is not None:
            return self._store
        if self._store_factory is None:
            return SQLiteCodeProjectionStore.open_read_only(database_path, policy_revision=policy_revision)
        return self._store_factory(database_path, policy_revision)


# The name used in the design is also exported for adapter readability.
CodeFreshness = CodeFreshnessService


def _entries_from_catalog(
    catalog: CodeRepositoryCatalog | Iterable[CodeRepositoryEntry],
) -> tuple[CodeRepositoryEntry, ...]:
    if hasattr(catalog, "entries"):
        values = catalog.entries()
    else:
        values = tuple(catalog)
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
    payload = [
        (entry.repository_id, repository_policy_revision(entry))
        for entry in sorted(entries, key=lambda item: item.repository_id)
    ]
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"code-policy-set-v1:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _pending_paths(projection: CodeProjectionStore, repository_ids: tuple[str, ...]) -> tuple[str, ...]:
    method = getattr(projection, "pending_paths", None)
    if callable(method):
        return tuple(str(path) for path in method(repository_ids))
    method = getattr(projection, "pending_references", None)
    if callable(method):
        return tuple(str(item.target_key) for item in method(repository_ids))
    return ()


def _last_freshness(projection: CodeProjectionStore) -> tuple[str, tuple[str, ...]]:
    method = getattr(projection, "last_freshness", None)
    if not callable(method):
        return "fresh", ()
    state, warnings = method()
    if state not in {"fresh", "stale", "syncing", "partial", "unavailable", "unknown"}:
        return "unknown", ("stored freshness state is invalid",)
    return state, tuple(warnings)


__all__ = ["CodeFreshness", "CodeFreshnessService"]
