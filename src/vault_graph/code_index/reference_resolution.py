"""Deterministic resolution of syntax-backed code graph references.

Parsing deliberately stops at static candidates.  This module turns those
candidates into confident graph edges only when one repository-local symbol is
unambiguously identified.  Missing targets are retained as pending records;
dynamic dispatch and collisions are represented as ambiguous edges and are
never guessed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CodeEdgeRecord,
    CodeFileSnapshot,
    CodeReferenceRecord,
    CodeSymbolRecord,
    PendingCodeReference,
    ResolutionResult,
)
from vault_graph.code_index.tree_sitter_parsing import stable_identity

_RESOLVABLE_RELATIONS = frozenset({"IMPORTS", "CALLS", "EXTENDS", "IMPLEMENTS", "TESTS", "DEFINES", "CONTAINS"})
_INHERITANCE_KINDS = frozenset({"class", "interface", "mixin"})
_DYNAMIC_MARKERS = ("(", ")", "[", "]", "<dynamic>", "<unknown>", "lambda", "=>")


@dataclass(frozen=True)
class _SymbolIndexes:
    by_id: dict[str, CodeSymbolRecord]
    by_qualified: dict[tuple[str, str], tuple[CodeSymbolRecord, ...]]
    by_name: dict[tuple[str, str], tuple[CodeSymbolRecord, ...]]
    modules_by_file: dict[str, CodeSymbolRecord]
    files_by_id: dict[str, CodeFileSnapshot]


class CodeReferenceResolver:
    """Resolve parser candidates using only repository-local static metadata."""

    def __init__(self, *, parser_spec_version: str = CODE_PARSER_SPEC_VERSION) -> None:
        self._parser_spec_version = parser_spec_version

    def resolve(
        self,
        *,
        files: tuple[CodeFileSnapshot, ...],
        symbols: tuple[CodeSymbolRecord, ...],
        references: tuple[CodeReferenceRecord, ...],
        previous_pending: tuple[PendingCodeReference, ...],
        changed_file_ids: tuple[str, ...] | None = None,
    ) -> ResolutionResult:
        """Return stable edges and pending retries for one projection scope.

        ``changed_file_ids`` is optional because full rebuilds have no change
        set.  Incremental callers may provide it to limit retries to pending
        references whose source or candidate target namespace was affected.
        Repository IDs are part of every lookup key, so similarly named files
        in separate registered repositories can never resolve to one another.
        """

        file_by_id: dict[str, CodeFileSnapshot] = {}
        for file in files:
            if file.parser_spec_version != self._parser_spec_version:
                raise ValueError("file parser_spec_version does not match resolver")
            file_id = self._file_id(file)
            if file_id in file_by_id and file_by_id[file_id] != file:
                raise ValueError(f"duplicate file identity: {file_id}")
            file_by_id[file_id] = file
        self._validate_symbol_scope(file_by_id, symbols)
        indexes = self._build_indexes(symbols, file_by_id)
        import_references = self._imports_by_file(references)
        valid_previous = self._validate_previous_pending(file_by_id, previous_pending)
        previous_by_reference = {(pending.repository_id, pending.reference_id): pending for pending in valid_previous}
        self._validate_reference_scope(references)
        changed = set(changed_file_ids) if changed_file_ids is not None else None
        edges: list[CodeEdgeRecord] = []
        pending: list[PendingCodeReference] = []
        retried: list[str] = []
        seen_edge_keys: set[tuple[str, str, str | None, str | None, int, int]] = set()
        seen_pending_keys: set[tuple[str, str, str, str]] = set()
        seen_references: set[tuple[str, str]] = set()

        for reference in sorted(references, key=_reference_sort_key):
            if reference.parser_spec_version != self._parser_spec_version:
                raise ValueError("reference parser_spec_version does not match resolver")
            source_file = file_by_id.get(reference.source_file_id)
            if source_file is None:
                raise ValueError(f"reference source_file_id is missing: {reference.source_file_id}")
            if source_file.repository_id != reference.repository_id:
                raise ValueError("reference source file must belong to the same repository")
            reference_scope = (reference.repository_id, reference.reference_id)
            seen_references.add(reference_scope)
            source_symbol = self._source_symbol(reference, indexes)
            candidates = self._candidates(
                reference,
                source_file,
                source_symbol,
                indexes,
                import_references,
            )
            previous = previous_by_reference.get(reference_scope)
            impacted = previous is not None and self._retry_is_impacted(
                reference,
                source_file,
                candidates,
                changed,
                indexes,
            )
            deferred = previous is not None and changed is not None and not impacted
            if deferred:
                # An incremental run must not consume a pending record merely
                # because an unrelated file happened to expose a same-named
                # symbol. Keep the old unresolved state until its namespace
                # or source file is actually affected.
                candidates = ()
            status: str
            target: CodeSymbolRecord | None
            reason: str | None = None
            if deferred:
                assert previous is not None
                status, target, reason = "unresolved", None, previous.reason
            elif not candidates and self._is_dynamic(reference):
                status, target, reason = "ambiguous", None, "dynamic-static-target"
            elif len(candidates) > 1:
                status, target, reason = "ambiguous", None, "multiple-static-targets"
            elif len(candidates) == 1:
                status, target = "inferred", candidates[0]
            else:
                status, target = "unresolved", None
                reason = "target-not-found"

            edge = self._edge(reference, source_symbol, target, status, reason)
            edge_key = _edge_key(edge)
            if edge_key not in seen_edge_keys:
                seen_edge_keys.add(edge_key)
                edges.append(edge)
            if status == "unresolved":
                record = (
                    previous
                    if deferred and previous is not None
                    else self._pending(
                        reference,
                        source_file,
                        reason or "target-not-found",
                    )
                )
                pending_key = _pending_key(record)
                if pending_key not in seen_pending_keys:
                    seen_pending_keys.add(pending_key)
                    pending.append(record)
            if previous is not None and (changed is None or impacted):
                retried.append(reference.reference_id)

        # A changed source file may temporarily produce no references (for
        # example after a syntax error). Keep unaffected pending records until
        # that source is parsed successfully again.
        if changed is None:
            return ResolutionResult(
                edges=tuple(sorted(edges, key=_edge_sort_key)),
                pending_references=tuple(sorted(pending, key=_pending_sort_key)),
                retried_reference_ids=tuple(sorted(set(retried))),
            )
        for old in sorted(valid_previous, key=lambda item: (item.repository_id, item.pending_id)):
            if (old.repository_id, old.reference_id) in seen_references or old.source_file_id not in file_by_id:
                continue
            if changed is not None and old.source_file_id in changed:
                continue
            key = _pending_key(old)
            if key not in seen_pending_keys:
                seen_pending_keys.add(key)
                pending.append(old)

        return ResolutionResult(
            edges=tuple(sorted(edges, key=_edge_sort_key)),
            pending_references=tuple(sorted(pending, key=_pending_sort_key)),
            retried_reference_ids=tuple(sorted(set(retried))),
        )

    @staticmethod
    def _file_id(file: CodeFileSnapshot) -> str:
        from vault_graph.code_index.code_models import code_file_identity

        return code_file_identity(file.repository_id, file.relative_path)

    def _build_indexes(
        self,
        symbols: tuple[CodeSymbolRecord, ...],
        files_by_id: dict[str, CodeFileSnapshot],
    ) -> _SymbolIndexes:
        by_id: dict[str, CodeSymbolRecord] = {}
        qualified: dict[tuple[str, str], list[CodeSymbolRecord]] = defaultdict(list)
        by_name: dict[tuple[str, str], list[CodeSymbolRecord]] = defaultdict(list)
        modules_by_file: dict[str, CodeSymbolRecord] = {}
        for symbol in symbols:
            if symbol.parser_spec_version != self._parser_spec_version:
                raise ValueError("symbol parser_spec_version does not match resolver")
            if symbol.symbol_id in by_id and by_id[symbol.symbol_id] != symbol:
                raise ValueError(f"duplicate symbol identity: {symbol.symbol_id}")
            by_id[symbol.symbol_id] = symbol
            qualified[(symbol.repository_id, symbol.qualified_name)].append(symbol)
            by_name[(symbol.repository_id, symbol.name)].append(symbol)
            if symbol.kind == "module":
                current = modules_by_file.get(symbol.file_id)
                if current is None or _symbol_sort_key(symbol) < _symbol_sort_key(current):
                    modules_by_file[symbol.file_id] = symbol
        return _SymbolIndexes(
            by_id=by_id,
            by_qualified={key: tuple(sorted(value, key=_symbol_sort_key)) for key, value in qualified.items()},
            by_name={key: tuple(sorted(value, key=_symbol_sort_key)) for key, value in by_name.items()},
            modules_by_file=modules_by_file,
            files_by_id=files_by_id,
        )

    @staticmethod
    def _validate_reference_scope(references: tuple[CodeReferenceRecord, ...]) -> None:
        seen: set[tuple[str, str]] = set()
        for reference in references:
            scope = (reference.repository_id, reference.reference_id)
            if scope in seen:
                raise ValueError(f"duplicate reference identity: {reference.repository_id}/{reference.reference_id}")
            seen.add(scope)

    def _validate_previous_pending(
        self,
        file_by_id: dict[str, CodeFileSnapshot],
        previous_pending: tuple[PendingCodeReference, ...],
    ) -> tuple[PendingCodeReference, ...]:
        valid: list[PendingCodeReference] = []
        seen_ids: set[str] = set()
        seen_scopes: set[tuple[str, str]] = set()
        for pending in previous_pending:
            if pending.pending_id in seen_ids:
                raise ValueError(f"duplicate pending reference identity: {pending.pending_id}")
            seen_ids.add(pending.pending_id)
            scope = (pending.repository_id, pending.reference_id)
            if scope in seen_scopes:
                raise ValueError(f"duplicate pending reference scope: {pending.repository_id}/{pending.reference_id}")
            seen_scopes.add(scope)
            if pending.parser_spec_version != self._parser_spec_version:
                raise ValueError("pending reference parser_spec_version is incompatible")
            source_file = file_by_id.get(pending.source_file_id)
            if source_file is None:
                continue
            if source_file.repository_id != pending.repository_id:
                raise ValueError("pending source file must belong to the same repository")
            if source_file.source_revision != pending.source_revision:
                # The source changed; current parser output owns the new
                # pending record and the old one must not be carried forward.
                continue
            valid.append(pending)
        return tuple(valid)

    def _validate_symbol_scope(
        self,
        file_by_id: dict[str, CodeFileSnapshot],
        symbols: tuple[CodeSymbolRecord, ...],
    ) -> None:
        for symbol in symbols:
            if symbol.file_id not in file_by_id:
                raise ValueError(f"symbol file_id is missing: {symbol.file_id}")
            source_file = file_by_id[symbol.file_id]
            if symbol.repository_id != source_file.repository_id:
                raise ValueError("symbol and file must belong to the same repository")
            if symbol.content_hash != source_file.content_hash or symbol.source_revision != source_file.source_revision:
                raise ValueError("symbol source identity does not match file")

    @staticmethod
    def _imports_by_file(references: tuple[CodeReferenceRecord, ...]) -> dict[str, tuple[str, ...]]:
        imports: dict[str, set[str]] = defaultdict(set)
        for reference in references:
            if reference.relation_kind == "IMPORTS":
                imports[reference.source_file_id].add(reference.target_key)
        return {file_id: tuple(sorted(values)) for file_id, values in imports.items()}

    @staticmethod
    def _source_symbol(reference: CodeReferenceRecord, indexes: _SymbolIndexes) -> CodeSymbolRecord:
        if reference.source_symbol_id is not None:
            symbol = indexes.by_id.get(reference.source_symbol_id)
            if symbol is None:
                raise ValueError(f"reference source_symbol_id is missing: {reference.source_symbol_id}")
            if symbol.repository_id != reference.repository_id:
                raise ValueError("reference source symbol must belong to the same repository")
            if symbol.file_id != reference.source_file_id:
                raise ValueError("reference source symbol must belong to the reference source file")
            return symbol
        module = indexes.modules_by_file.get(reference.source_file_id)
        if module is None:
            raise ValueError("reference without source_symbol_id requires a module symbol for its source file")
        return module

    def _candidates(
        self,
        reference: CodeReferenceRecord,
        source_file: CodeFileSnapshot,
        source_symbol: CodeSymbolRecord,
        indexes: _SymbolIndexes,
        import_references: dict[str, tuple[str, ...]],
    ) -> tuple[CodeSymbolRecord, ...]:
        target_key = _clean_target(reference.target_key)
        if not target_key:
            return ()
        repository_id = reference.repository_id
        if reference.relation_kind == "IMPORTS":
            return self._import_candidates(target_key, source_file, repository_id, indexes)
        if reference.relation_kind not in _RESOLVABLE_RELATIONS:
            return ()

        candidates: list[CodeSymbolRecord] = []
        module = indexes.modules_by_file.get(source_file_id := self._file_id(source_file))
        module_name = module.qualified_name if module is not None else _module_from_path(source_file.relative_path)
        source_module = module_name
        if source_symbol.kind != "module":
            source_module = source_symbol.qualified_name.rsplit(".", 1)[0]
        if reference.relation_kind in {"EXTENDS", "IMPLEMENTS"}:
            allowed = _INHERITANCE_KINDS
        elif reference.relation_kind in {"CALLS", "TESTS"}:
            allowed = frozenset({"class", "function", "method", "property", "test"})
        else:
            allowed = frozenset({"module", "class", "interface", "mixin", "function", "method", "property", "test"})

        def add(values: Iterable[CodeSymbolRecord]) -> None:
            for candidate in values:
                if candidate.repository_id == repository_id and candidate.kind in allowed:
                    candidates.append(candidate)

        # Exact qualified identity is the strongest static evidence.
        add(indexes.by_qualified.get((repository_id, target_key), ()))
        if not candidates and target_key.startswith("."):
            add(indexes.by_qualified.get((repository_id, _relative_module(source_module, target_key)), ()))
        if not candidates and "." in target_key:
            add(indexes.by_qualified.get((repository_id, f"{source_module}.{target_key}"), ()))

        # Resolve imported module members (``from package.module import Name``)
        # when the parser supplied the module import as a separate candidate.
        if not candidates:
            for imported in import_references.get(source_file_id, ()):
                imported_module = _normal_module_name(imported)
                if imported_module:
                    add(indexes.by_qualified.get((repository_id, f"{imported_module}.{target_key}"), ()))

        # Same-file names are preferred over a repository-wide short name.
        if not candidates and "." not in target_key:
            add(
                symbol
                for symbol in indexes.by_name.get((repository_id, target_key.rsplit(".", 1)[-1]), ())
                if symbol.file_id == source_file_id
            )
        if not candidates and "." not in target_key:
            add(indexes.by_name.get((repository_id, target_key.rsplit(".", 1)[-1]), ()))

        # A suffix match is useful for language-qualified names but remains
        # ambiguous when more than one declaration shares that suffix.
        if not candidates and "." in target_key:
            suffix = "." + target_key
            add(
                symbol
                for (repo, qualified_name), values in indexes.by_qualified.items()
                if repo == repository_id and qualified_name.endswith(suffix)
                for symbol in values
            )
        return _unique_symbols(candidates)

    def _import_candidates(
        self,
        target_key: str,
        source_file: CodeFileSnapshot,
        repository_id: str,
        indexes: _SymbolIndexes,
    ) -> tuple[CodeSymbolRecord, ...]:
        module = indexes.modules_by_file.get(self._file_id(source_file))
        source_module = module.qualified_name if module is not None else _module_from_path(source_file.relative_path)
        normalized = _normal_module_name(target_key)
        candidates: list[CodeSymbolRecord] = []
        for candidate_name in (
            normalized,
            _relative_module(source_module, target_key) if target_key.startswith(".") else "",
            f"{source_module.rsplit('.', 1)[0]}.{normalized}" if normalized and "." not in normalized else "",
        ):
            if not candidate_name:
                continue
            candidates.extend(indexes.by_qualified.get((repository_id, candidate_name), ()))
        if not candidates:
            normalized_path = normalized.replace(".", "/") if normalized else ""
            for candidate in indexes.modules_by_file.values():
                if candidate.repository_id != repository_id:
                    continue
                candidate_path = candidate.qualified_name.replace(".", "/")
                candidate_file = indexes.files_by_id.get(candidate.file_id)
                if (
                    candidate_path == normalized_path
                    or _module_from_path(candidate_path) == normalized
                    or (
                        candidate_file is not None
                        and _matches_import_path(candidate_file.relative_path, normalized_path)
                    )
                ):
                    candidates.append(candidate)
        return _unique_symbols(symbol for symbol in candidates if symbol.kind == "module")

    def _retry_is_impacted(
        self,
        reference: CodeReferenceRecord,
        source_file: CodeFileSnapshot,
        candidates: tuple[CodeSymbolRecord, ...],
        changed_file_ids: set[str] | None,
        indexes: _SymbolIndexes,
    ) -> bool:
        if changed_file_ids is None:
            return True
        if self._file_id(source_file) in changed_file_ids:
            return True
        if any(candidate.file_id in changed_file_ids for candidate in candidates):
            return True
        target = _clean_target(reference.target_key)
        if not target:
            return False
        normalized_target = _normal_module_name(target.lstrip(".")).replace(".", "/")
        for file_id in changed_file_ids:
            changed_file = indexes.files_by_id.get(file_id)
            if changed_file is None or changed_file.repository_id != reference.repository_id:
                continue
            module = indexes.modules_by_file.get(file_id)
            if module is not None and (
                module.qualified_name == target
                or module.qualified_name.endswith("." + target)
                or _normal_module_name(module.qualified_name) == _normal_module_name(target)
            ):
                return True
            if _matches_import_path(changed_file.relative_path, normalized_target):
                return True
            if any(
                symbol.file_id == file_id
                and symbol.repository_id == reference.repository_id
                and (symbol.name == target.rsplit(".", 1)[-1] or symbol.qualified_name == target)
                for symbol in indexes.by_id.values()
            ):
                return True
        return False

    def _edge(
        self,
        reference: CodeReferenceRecord,
        source_symbol: CodeSymbolRecord,
        target: CodeSymbolRecord | None,
        status: str,
        reason: str | None,
    ) -> CodeEdgeRecord:
        unresolved_key = None if target is not None else _clean_target(reference.target_key)
        return CodeEdgeRecord(
            edge_id=stable_identity(
                "code-edge-v1",
                reference.repository_id,
                source_symbol.symbol_id,
                reference.relation_kind,
                target.symbol_id if target is not None else unresolved_key or "",
                str(reference.anchor_start_line),
                str(reference.anchor_start_column),
                reference.parser_spec_version,
            ),
            repository_id=reference.repository_id,
            source_symbol_id=source_symbol.symbol_id,
            relation_kind=reference.relation_kind,
            target_symbol_id=target.symbol_id if target is not None else None,
            unresolved_target_key=unresolved_key,
            extraction_status=status,  # type: ignore[arg-type]
            anchor_start_line=reference.anchor_start_line,
            anchor_start_column=reference.anchor_start_column,
            parser_spec_version=reference.parser_spec_version,
        )

    @staticmethod
    def _pending(
        reference: CodeReferenceRecord,
        source_file: CodeFileSnapshot,
        reason: str,
    ) -> PendingCodeReference:
        return PendingCodeReference(
            pending_id=stable_identity(
                "code-pending-v1",
                reference.repository_id,
                reference.source_file_id,
                reference.reference_id,
                reference.relation_kind,
                _pending_namespace(reference.target_key, reason),
            ),
            repository_id=reference.repository_id,
            source_file_id=reference.source_file_id,
            reference_id=reference.reference_id,
            source_revision=source_file.source_revision,
            relation_kind=reference.relation_kind,
            target_key=_pending_namespace(reference.target_key, reason),
            reason=reason,
            parser_spec_version=reference.parser_spec_version,
        )

    @staticmethod
    def _is_dynamic(reference: CodeReferenceRecord) -> bool:
        target = reference.target_key.casefold()
        return reference.relation_kind in {"CALLS", "TESTS"} and (
            target.startswith("dynamic:") or any(marker in target for marker in (*_DYNAMIC_MARKERS, "."))
        )


def _clean_target(target: str) -> str:
    return target.strip().strip("'\"")


def _normal_module_name(target: str) -> str:
    value = _clean_target(target).removeprefix("package:")
    value = value.replace("\\", "/")
    if value.startswith("dart:"):
        return value
    if value.endswith(".py") or value.endswith(".dart"):
        value = value.rsplit(".", 1)[0]
    return value.strip("/").replace("/", ".")


def _module_from_path(path: str) -> str:
    value = PurePosixPath(path.replace("\\", "/"))
    name = str(value.with_suffix(""))
    if name.endswith(".__init__"):
        name = name[: -len(".__init__")]
    return name.replace("/", ".")


def _matches_import_path(relative_path: str, normalized_target: str) -> bool:
    """Match package/URI imports to a repository-relative source path.

    Dart package names are not necessarily represented in a library
    declaration. Comparing suffixes lets ``package:pkg/src/foo.dart`` resolve
    to ``lib/src/foo.dart`` without treating the external package as a local
    source authority.
    """

    if not normalized_target:
        return False
    path = relative_path.replace("\\", "/").lstrip("/")
    target = normalized_target.strip("/")
    target_parts = target.split("/")
    candidates = {target, "/".join(target_parts[1:]) if len(target_parts) > 1 else target}
    for candidate in candidates:
        for extension in ("", ".py", ".dart"):
            expected = candidate + extension
            if path == expected or path.endswith("/" + expected):
                return True
    return False


def _relative_module(source_module: str, target: str) -> str:
    dots = len(target) - len(target.lstrip("."))
    suffix = _normal_module_name(target.lstrip("."))
    parts = source_module.split(".")
    # Python's one-dot import is relative to the current package, not the
    # current module. Additional dots walk up one package per extra dot.
    base = parts[: max(0, len(parts) - dots)]
    return ".".join((*base, suffix)) if suffix else ".".join(base)


def _pending_namespace(target: str, reason: str | None) -> str:
    target = _clean_target(target)
    if reason == "dynamic-static-target":
        return f"dynamic:{target}"
    return target


def _unique_symbols(symbols: Iterable[CodeSymbolRecord]) -> tuple[CodeSymbolRecord, ...]:
    unique = {symbol.symbol_id: symbol for symbol in symbols}
    return tuple(sorted(unique.values(), key=_symbol_sort_key))


def _symbol_sort_key(symbol: CodeSymbolRecord) -> tuple[str, str, int, int, str]:
    return (symbol.repository_id, symbol.qualified_name, symbol.start_line, symbol.start_column, symbol.symbol_id)


def _reference_sort_key(reference: CodeReferenceRecord) -> tuple[str, str, int, int, str, str]:
    return (
        reference.repository_id,
        reference.source_file_id,
        reference.anchor_start_line,
        reference.anchor_start_column,
        reference.relation_kind,
        reference.reference_id,
    )


def _edge_key(edge: CodeEdgeRecord) -> tuple[str, str, str | None, str | None, int, int]:
    return (
        edge.source_symbol_id,
        edge.relation_kind,
        edge.target_symbol_id,
        edge.unresolved_target_key,
        edge.anchor_start_line,
        edge.anchor_start_column,
    )


def _edge_sort_key(edge: CodeEdgeRecord) -> tuple[str, str, str, int, int, str]:
    return (
        edge.repository_id,
        edge.source_symbol_id,
        edge.relation_kind,
        edge.anchor_start_line,
        edge.anchor_start_column,
        edge.edge_id,
    )


def _pending_key(pending: PendingCodeReference) -> tuple[str, str, str, str]:
    return (pending.repository_id, pending.source_file_id, pending.relation_kind, pending.target_key)


def _pending_sort_key(pending: PendingCodeReference) -> tuple[str, str, str, str, str]:
    return (
        pending.repository_id,
        pending.source_file_id,
        pending.relation_kind,
        pending.target_key,
        pending.pending_id,
    )
