from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CodeFileSnapshot,
    CodeReferenceRecord,
    CodeSymbolRecord,
    code_file_identity,
)
from vault_graph.code_index.reference_resolution import CodeReferenceResolver


def _file(repository_id: str, path: str, revision: str = "revision") -> CodeFileSnapshot:
    content = f"# {path}\n".encode()
    return CodeFileSnapshot(
        repository_id=repository_id,
        relative_path=path,
        language="python",
        content_hash=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        line_count=1,
        source_revision=revision,
        is_test_file=path.startswith("tests/"),
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )


def _symbol(
    file: CodeFileSnapshot,
    name: str,
    *,
    kind: str = "function",
    qualified_name: str | None = None,
    line: int = 1,
) -> CodeSymbolRecord:
    file_id = code_file_identity(file.repository_id, file.relative_path)
    qualified_name = qualified_name or f"{file.relative_path.removesuffix('.py').replace('/', '.')}.{name}"
    return CodeSymbolRecord(
        symbol_id=f"{file_id[:48]}-{name}-{line}",
        repository_id=file.repository_id,
        file_id=file_id,
        kind=kind,
        language_kind=kind,
        name=name,
        qualified_name=qualified_name,
        signature=None,
        start_line=line,
        end_line=line,
        start_column=0,
        end_column=len(name),
        content_hash=file.content_hash,
        source_revision=file.source_revision,
        parser_spec_version=file.parser_spec_version,
    )


def _reference(
    file: CodeFileSnapshot,
    source: CodeSymbolRecord | None,
    relation: str,
    target: str,
    *,
    line: int = 1,
    reference_id: str | None = None,
) -> CodeReferenceRecord:
    return CodeReferenceRecord(
        reference_id=reference_id or f"reference-{relation}-{target}-{line}",
        repository_id=file.repository_id,
        source_file_id=code_file_identity(file.repository_id, file.relative_path),
        source_symbol_id=source.symbol_id if source else None,
        relation_kind=relation,
        target_key=target,
        anchor_start_line=line,
        anchor_start_column=0,
        parser_spec_version=file.parser_spec_version,
    )


def test_resolves_same_file_and_cross_file_calls_without_cross_repository_edges() -> None:
    local = _file("repo", "pkg/service.py")
    dependency = _file("repo", "pkg/helper.py")
    foreign = _file("other", "pkg/helper.py")
    caller = _symbol(local, "run", kind="function", line=2)
    local_target = _symbol(local, "local", kind="function", line=4)
    remote_target = _symbol(dependency, "helper", kind="function", line=2)
    foreign_target = _symbol(foreign, "helper", kind="function", line=2)
    references = (
        _reference(local, caller, "CALLS", "local", line=3),
        _reference(local, caller, "CALLS", "helper", line=4),
    )

    result = CodeReferenceResolver().resolve(
        files=(local, dependency, foreign),
        symbols=(caller, local_target, remote_target, foreign_target),
        references=references,
        previous_pending=(),
    )

    assert {edge.target_symbol_id for edge in result.edges} == {local_target.symbol_id, remote_target.symbol_id}
    assert result.pending_references == ()
    assert all(edge.repository_id == "repo" for edge in result.edges)


def test_rejects_source_symbol_from_another_file_or_missing_symbol() -> None:
    source = _file("repo", "pkg/service.py")
    other = _file("repo", "pkg/other.py")
    caller = _symbol(source, "run", line=2)
    foreign = _symbol(other, "other", line=2)
    wrong_file = _reference(source, foreign, "CALLS", "missing", line=3)
    missing = replace(wrong_file, source_symbol_id="missing-source")

    with pytest.raises(ValueError, match="source symbol must belong to the reference source file"):
        CodeReferenceResolver().resolve(
            files=(source, other), symbols=(caller, foreign), references=(wrong_file,), previous_pending=()
        )
    with pytest.raises(ValueError, match="source_symbol_id is missing"):
        CodeReferenceResolver().resolve(
            files=(source, other), symbols=(caller, foreign), references=(missing,), previous_pending=()
        )


def test_rejects_source_less_reference_when_source_module_is_not_indexed() -> None:
    source = _file("repo", "pkg/service.py")
    caller = _symbol(source, "run", line=2)
    reference = replace(_reference(source, caller, "DEFINES", "pkg.service", line=1), source_symbol_id=None)

    with pytest.raises(ValueError, match="requires a module symbol"):
        CodeReferenceResolver().resolve(
            files=(source,), symbols=(caller,), references=(reference,), previous_pending=()
        )


def test_resolves_imports_inheritance_implements_and_test_targets() -> None:
    production = _file("repo", "pkg/service.py")
    base_file = _file("repo", "pkg/base.py")
    test_file = _file("repo", "tests/test_service.py")
    service = _symbol(production, "Service", kind="class", line=2)
    base = _symbol(base_file, "Base", kind="class", line=2)
    interface = _symbol(base_file, "Contract", kind="interface", line=4)
    test = _symbol(test_file, "test_service", kind="test", line=2)
    references = (
        _reference(production, service, "IMPORTS", "pkg.base", line=1),
        _reference(production, service, "EXTENDS", "Base", line=2),
        _reference(production, service, "IMPLEMENTS", "Contract", line=2),
        _reference(test_file, test, "TESTS", "Service", line=3),
    )

    result = CodeReferenceResolver().resolve(
        files=(production, base_file, test_file),
        symbols=(service, base, interface, test),
        references=references,
        previous_pending=(),
    )

    resolved = {(edge.relation_kind, edge.target_symbol_id) for edge in result.edges}
    assert ("IMPORTS", _symbol(base_file, "base", kind="module").symbol_id) not in resolved
    assert ("EXTENDS", base.symbol_id) in resolved
    assert ("IMPLEMENTS", interface.symbol_id) in resolved
    assert ("TESTS", service.symbol_id) in resolved
    assert any(edge.relation_kind == "IMPORTS" and edge.extraction_status == "unresolved" for edge in result.edges)


def test_resolves_package_and_relative_imports_to_module_symbols() -> None:
    source = _file("repo", "pkg/service.py")
    helper_file = _file("repo", "pkg/helper.py")
    base_file = _file("repo", "pkg/base.py")
    service = _symbol(source, "service", kind="module", qualified_name="pkg.service")
    helper = _symbol(helper_file, "helper", kind="module", qualified_name="pkg.helper")
    base = _symbol(base_file, "base", kind="module", qualified_name="pkg.base")
    references = (
        _reference(source, service, "IMPORTS", ".helper", line=1),
        _reference(source, service, "IMPORTS", "pkg.base", line=2),
    )

    result = CodeReferenceResolver().resolve(
        files=(source, helper_file, base_file),
        symbols=(service, helper, base),
        references=references,
        previous_pending=(),
    )

    assert {(edge.relation_kind, edge.target_symbol_id) for edge in result.edges} == {
        ("IMPORTS", helper.symbol_id),
        ("IMPORTS", base.symbol_id),
    }
    assert result.pending_references == ()


def test_resolves_package_uri_against_repository_relative_source_path() -> None:
    source = _file("repo", "lib/main.py")
    package_file = _file("repo", "lib/src/foo.py")
    main = _symbol(source, "main", kind="module", qualified_name="main")
    package_module = _symbol(package_file, "foo", kind="module", qualified_name="foo")
    reference = _reference(source, main, "IMPORTS", "pkg.src.foo", line=1)

    result = CodeReferenceResolver().resolve(
        files=(source, package_file),
        symbols=(main, package_module),
        references=(reference,),
        previous_pending=(),
    )

    assert result.edges[0].target_symbol_id == package_module.symbol_id
    assert result.pending_references == ()


def test_duplicate_reference_collapses_to_one_edge_and_missing_target_is_pending() -> None:
    file = _file("repo", "pkg/service.py")
    caller = _symbol(file, "run", line=2)
    references = (
        _reference(file, caller, "CALLS", "missing", line=3, reference_id="first"),
        _reference(file, caller, "CALLS", "missing", line=3, reference_id="second"),
    )

    result = CodeReferenceResolver().resolve(
        files=(file,), symbols=(caller,), references=references, previous_pending=()
    )

    assert len(result.edges) == 1
    assert result.edges[0].extraction_status == "unresolved"
    assert result.edges[0].unresolved_target_key == "missing"
    assert len(result.pending_references) == 1
    assert result.pending_references[0].source_file_id == code_file_identity("repo", "pkg/service.py")


def test_pending_reference_retries_when_target_file_is_added() -> None:
    source = _file("repo", "pkg/service.py", revision="source")
    pending_target = _file("repo", "pkg/helper.py", revision="target")
    caller = _symbol(source, "run", line=2)
    reference = _reference(source, caller, "CALLS", "helper", line=3, reference_id="retry-me")
    first = CodeReferenceResolver().resolve(
        files=(source,), symbols=(caller,), references=(reference,), previous_pending=()
    )
    second = CodeReferenceResolver().resolve(
        files=(source, pending_target),
        symbols=(caller, _symbol(pending_target, "helper", line=2)),
        references=(reference,),
        previous_pending=first.pending_references,
    )

    assert second.pending_references == ()
    assert second.retried_reference_ids == ("retry-me",)
    assert second.edges[0].extraction_status == "inferred"


def test_parser_spec_version_is_part_of_edge_identity() -> None:
    source = _file("repo", "pkg/service.py")
    target = _file("repo", "pkg/helper.py")
    caller = _symbol(source, "run", line=2)
    helper = _symbol(target, "helper", line=2)
    reference = _reference(source, caller, "CALLS", "helper", line=3)
    first = CodeReferenceResolver().resolve(
        files=(source, target), symbols=(caller, helper), references=(reference,), previous_pending=()
    )
    newer_spec = "code-parser-spec-v2"
    second = CodeReferenceResolver(parser_spec_version=newer_spec).resolve(
        files=(replace(source, parser_spec_version=newer_spec), replace(target, parser_spec_version=newer_spec)),
        symbols=(replace(caller, parser_spec_version=newer_spec), replace(helper, parser_spec_version=newer_spec)),
        references=(replace(reference, parser_spec_version=newer_spec),),
        previous_pending=(),
    )

    assert first.edges[0].edge_id != second.edges[0].edge_id


def test_incremental_retry_skips_unrelated_changes_and_reports_impacted_unresolved() -> None:
    source = _file("repo", "pkg/service.py")
    target = _file("repo", "pkg/helper.py")
    unrelated = _file("repo", "pkg/other.py")
    caller = _symbol(source, "run", line=2)
    reference = _reference(source, caller, "CALLS", "helper", line=3, reference_id="retry-me")
    first = CodeReferenceResolver().resolve(
        files=(source,), symbols=(caller,), references=(reference,), previous_pending=()
    )

    unrelated_run = CodeReferenceResolver().resolve(
        files=(source, target, unrelated),
        symbols=(caller,),
        references=(reference,),
        previous_pending=first.pending_references,
        changed_file_ids=(code_file_identity("repo", "pkg/other.py"),),
    )
    impacted_run = CodeReferenceResolver().resolve(
        files=(source, target),
        symbols=(caller,),
        references=(reference,),
        previous_pending=first.pending_references,
        changed_file_ids=(code_file_identity("repo", "pkg/helper.py"),),
    )

    assert unrelated_run.retried_reference_ids == ()
    assert len(unrelated_run.pending_references) == 1
    assert impacted_run.retried_reference_ids == ("retry-me",)
    assert len(impacted_run.pending_references) == 1


def test_full_rebuild_drops_pending_references_missing_from_current_parse() -> None:
    source = _file("repo", "pkg/service.py")
    caller = _symbol(source, "run", line=2)
    reference = _reference(source, caller, "CALLS", "missing", line=3, reference_id="stale")
    first = CodeReferenceResolver().resolve(
        files=(source,), symbols=(caller,), references=(reference,), previous_pending=()
    )

    rebuilt = CodeReferenceResolver().resolve(
        files=(source,), symbols=(caller,), references=(), previous_pending=first.pending_references
    )

    assert rebuilt.pending_references == ()


def test_pending_identity_is_scoped_by_repository_when_reference_ids_collide() -> None:
    first_file = _file("first", "pkg/service.py")
    second_file = _file("second", "pkg/service.py")
    first_caller = _symbol(first_file, "run", line=2)
    second_caller = _symbol(second_file, "run", line=2)
    first_reference = _reference(first_file, first_caller, "CALLS", "missing", line=3, reference_id="shared")
    second_reference = _reference(second_file, second_caller, "CALLS", "missing", line=3, reference_id="shared")
    initial = CodeReferenceResolver().resolve(
        files=(first_file, second_file),
        symbols=(first_caller, second_caller),
        references=(first_reference, second_reference),
        previous_pending=(),
    )

    incremental = CodeReferenceResolver().resolve(
        files=(first_file, second_file),
        symbols=(first_caller, second_caller),
        references=(first_reference,),
        previous_pending=initial.pending_references,
        changed_file_ids=(code_file_identity("first", "pkg/other.py"),),
    )

    assert {pending.repository_id for pending in incremental.pending_references} == {"first", "second"}


def test_rejects_duplicate_current_reference_scope() -> None:
    source = _file("repo", "pkg/service.py")
    caller = _symbol(source, "run", line=2)
    first = _reference(source, caller, "CALLS", "one", line=3, reference_id="duplicate")
    second = _reference(source, caller, "CALLS", "two", line=4, reference_id="duplicate")

    with pytest.raises(ValueError, match="duplicate reference identity"):
        CodeReferenceResolver().resolve(
            files=(source,), symbols=(caller,), references=(first, second), previous_pending=()
        )


def test_rejects_duplicate_previous_pending_scope() -> None:
    source = _file("repo", "pkg/service.py")
    caller = _symbol(source, "run", line=2)
    reference = _reference(source, caller, "CALLS", "missing", line=3, reference_id="duplicate")
    initial = CodeReferenceResolver().resolve(
        files=(source,), symbols=(caller,), references=(reference,), previous_pending=()
    )
    first = initial.pending_references[0]
    second = replace(first, pending_id=f"{first.pending_id}-duplicate")

    with pytest.raises(ValueError, match="duplicate pending reference scope"):
        CodeReferenceResolver().resolve(
            files=(source,),
            symbols=(caller,),
            references=(reference,),
            previous_pending=(first, second),
        )


def test_collisions_and_dynamic_calls_are_ambiguous_not_confident() -> None:
    source = _file("repo", "pkg/service.py")
    first_file = _file("repo", "pkg/one.py")
    second_file = _file("repo", "pkg/two.py")
    caller = _symbol(source, "run", line=2)
    first = _symbol(first_file, "helper", line=2)
    second = _symbol(second_file, "helper", line=2)
    method = _symbol(first_file, "method", line=4)
    marker_collision = _symbol(
        first_file,
        "obj.method",
        qualified_name="dynamic:obj.method",
        line=5,
    )
    references = (
        _reference(source, caller, "CALLS", "helper", line=3),
        _reference(source, caller, "CALLS", "factory()", line=4),
        _reference(source, caller, "CALLS", "dynamic:obj.method", line=5),
    )

    result = CodeReferenceResolver().resolve(
        files=(source, first_file, second_file),
        symbols=(caller, first, second, method, marker_collision),
        references=references,
        previous_pending=(),
    )

    assert len(result.edges) == 3
    assert all(edge.extraction_status == "ambiguous" for edge in result.edges)
    assert all(edge.target_symbol_id is None for edge in result.edges)
    assert result.pending_references == ()
