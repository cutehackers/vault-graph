from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import cast

import pytest

from vault_graph.code_index.code_models import (
    CODE_EXTRACTION_STATUSES,
    CODE_FRESHNESS_STATES,
    CODE_PARSER_SPEC_VERSION,
    CODE_PROJECTION_SCHEMA_VERSION,
    CODE_RELATION_KINDS,
    CODE_SYMBOL_KINDS,
    CodeApplyResult,
    CodeEdgeRecord,
    CodeFileInput,
    CodeFileSnapshot,
    CodeFreshnessReport,
    CodeFreshnessRequest,
    CodeIndexPlan,
    CodeIndexRequest,
    CodeManifest,
    CodeParseDiagnostic,
    CodeParseResult,
    CodeReconcilePlan,
    CodeReferenceRecord,
    CodeRepositoryAddRequest,
    CodeRepositoryEntry,
    CodeRunReport,
    CodeSymbolHit,
    CodeSymbolQuery,
    CodeSymbolRecord,
    CodeTraversalQuery,
    CodeTraversalResult,
    PendingCodeReference,
)


def _file() -> CodeFileSnapshot:
    return CodeFileSnapshot(
        repository_id="demo",
        relative_path="lib/example.py",
        language="python",
        content_hash="a" * 64,
        byte_count=20,
        line_count=3,
        source_revision="content-hash:a",
        is_test_file=False,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )


def _symbol() -> CodeSymbolRecord:
    return CodeSymbolRecord(
        symbol_id="symbol-1",
        repository_id="demo",
        file_id="file-1",
        kind="function",
        language_kind="function_definition",
        name="hello",
        qualified_name="example.hello",
        signature="hello(name)",
        start_line=1,
        end_line=3,
        start_column=0,
        end_column=17,
        content_hash="a" * 64,
        source_revision="content-hash:a",
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )


def test_primary_records_are_frozen_and_expose_parser_versions() -> None:
    repository = CodeRepositoryEntry(
        repository_id="demo",
        root_path=Path("/tmp/demo"),
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(".venv/**",),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="head-and-working-tree",
        watch=False,
    )
    file = _file()
    symbol = _symbol()
    edge = CodeEdgeRecord(
        edge_id="edge-1",
        repository_id="demo",
        source_symbol_id=symbol.symbol_id,
        relation_kind="CALLS",
        target_symbol_id=None,
        unresolved_target_key="example.other",
        extraction_status="unresolved",
        anchor_start_line=2,
        anchor_start_column=4,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )

    assert repository.repository_id == "demo"
    assert file.parser_spec_version == CODE_PARSER_SPEC_VERSION
    assert symbol.parser_spec_version == CODE_PARSER_SPEC_VERSION
    assert edge.extraction_status == "unresolved"
    with pytest.raises(FrozenInstanceError):
        file.line_count = 8  # type: ignore[misc]


def test_contract_enum_values_are_closed_and_stable() -> None:
    assert CODE_EXTRACTION_STATUSES == ("extracted", "inferred", "ambiguous", "unresolved")
    assert CODE_RELATION_KINDS == ("CONTAINS", "DEFINES", "IMPORTS", "CALLS", "EXTENDS", "IMPLEMENTS", "TESTS")
    assert "function" in CODE_SYMBOL_KINDS
    assert CODE_FRESHNESS_STATES == ("fresh", "stale", "syncing", "partial", "unavailable", "unknown")


def test_primary_records_reject_empty_identity_and_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="repository_id"):
        CodeFileSnapshot(
            repository_id="",
            relative_path="x.py",
            language="python",
            content_hash="a" * 64,
            byte_count=1,
            line_count=1,
            source_revision="rev",
            is_test_file=False,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )

    with pytest.raises(ValueError, match="relative_path"):
        CodeFileSnapshot(
            repository_id="demo",
            relative_path="",
            language="python",
            content_hash="a" * 64,
            byte_count=1,
            line_count=1,
            source_revision="rev",
            is_test_file=False,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )

    with pytest.raises(ValueError, match="line range"):
        CodeSymbolRecord(
            symbol_id="symbol-1",
            repository_id="demo",
            file_id="file-1",
            kind="function",
            language_kind="function_definition",
            name="hello",
            qualified_name="example.hello",
            signature=None,
            start_line=3,
            end_line=2,
            start_column=0,
            end_column=1,
            content_hash="a" * 64,
            source_revision="rev",
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )


def test_edge_rejects_invalid_extraction_status_and_anchor() -> None:
    with pytest.raises(ValueError, match="extraction_status"):
        CodeEdgeRecord(
            edge_id="edge-1",
            repository_id="demo",
            source_symbol_id="symbol-1",
            relation_kind="CALLS",
            target_symbol_id="symbol-2",
            unresolved_target_key=None,
            extraction_status="guesswork",  # type: ignore[arg-type]
            anchor_start_line=1,
            anchor_start_column=0,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )

    with pytest.raises(ValueError, match="resolved extraction"):
        CodeEdgeRecord(
            edge_id="edge-1",
            repository_id="demo",
            source_symbol_id="symbol-1",
            relation_kind="CALLS",
            target_symbol_id=None,
            unresolved_target_key=None,
            extraction_status="extracted",
            anchor_start_line=1,
            anchor_start_column=0,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )


def test_file_input_rejects_content_hash_mismatch() -> None:
    content = b"def hello():\n    return 1\n"
    with pytest.raises(ValueError, match="content_hash does not match content"):
        CodeFileInput(
            repository_id="demo",
            relative_path="lib/example.py",
            language="python",
            content=content,
            content_hash="a" * 64,
            source_revision="content-hash:a",
            is_test_file=False,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )

    valid = CodeFileInput(
        repository_id="demo",
        relative_path="lib/example.py",
        language="python",
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        source_revision="content-hash:valid",
        is_test_file=False,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    assert valid.snapshot().content_hash == hashlib.sha256(content).hexdigest()


def test_parse_result_rejects_dangling_reference_file_identity_and_anchor() -> None:
    expected_file_id = hashlib.sha256(b"code-file-v1\0demo\0lib/example.py").hexdigest()
    valid_reference = CodeReferenceRecord(
        reference_id="reference-1",
        repository_id="demo",
        source_file_id=expected_file_id,
        source_symbol_id=None,
        relation_kind="IMPORTS",
        target_key="other",
        anchor_start_line=3,
        anchor_start_column=0,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    valid = CodeParseResult(file=_file(), symbols=(), references=(valid_reference,))
    assert valid.references == (valid_reference,)

    with pytest.raises(ValueError, match="source_file_id"):
        CodeParseResult(file=_file(), symbols=(), references=(replace(valid_reference, source_file_id="other"),))
    with pytest.raises(ValueError, match="anchor_start_line"):
        CodeParseResult(file=_file(), symbols=(), references=(replace(valid_reference, anchor_start_line=0),))
    with pytest.raises(ValueError, match="anchor_start_line"):
        CodeParseResult(file=_file(), symbols=(), references=(replace(valid_reference, anchor_start_line=4),))
    with pytest.raises(ValueError, match="source_symbol_id"):
        CodeParseResult(
            file=_file(),
            symbols=(),
            references=(replace(valid_reference, source_symbol_id="dangling-symbol"),),
        )


def test_nested_sequences_are_normalized_to_immutable_tuples() -> None:
    languages = ["python"]
    include_globs = ["**/*.py"]
    manifest = CodeManifest(
        generation_id="generation-1",
        schema_version=CODE_PROJECTION_SCHEMA_VERSION,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
        repository_ids=cast(tuple[str, ...], ["demo"]),
        policy_revision="policy-1",
        source_revisions=cast(tuple[tuple[str, str], ...], [["demo", "rev-1"]]),
        file_ids=cast(tuple[str, ...], ["file-1"]),
    )
    request = CodeRepositoryAddRequest(
        repository_id="demo",
        root_path=Path("/tmp/demo"),
        display_name="Demo",
        languages=cast(tuple[str, ...], languages),
        include_globs=cast(tuple[str, ...], include_globs),
    )
    languages.append("dart")
    include_globs.append("**/*.dart")

    assert request.languages == ("python",)
    assert request.include_globs == ("**/*.py",)
    assert manifest.repository_ids == ("demo",)
    assert manifest.source_revisions == (("demo", "rev-1"),)
    assert manifest.file_ids == ("file-1",)


def test_manifest_rejects_malformed_revision_and_file_identity_entries() -> None:
    with pytest.raises(ValueError, match="source_revisions entries"):
        CodeManifest(
            generation_id="generation-1",
            schema_version=CODE_PROJECTION_SCHEMA_VERSION,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
            repository_ids=("demo",),
            policy_revision="policy-1",
            source_revisions=cast(tuple[tuple[str, str], ...], (("demo",),)),
        )
    with pytest.raises(ValueError, match="source_revisions.revision"):
        CodeManifest(
            generation_id="generation-1",
            schema_version=CODE_PROJECTION_SCHEMA_VERSION,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
            repository_ids=("demo",),
            policy_revision="policy-1",
            source_revisions=(("demo", ""),),
        )
    with pytest.raises(ValueError, match="file_ids"):
        CodeManifest(
            generation_id="generation-1",
            schema_version=CODE_PROJECTION_SCHEMA_VERSION,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
            repository_ids=("demo",),
            policy_revision="policy-1",
            file_ids=("",),
        )


def test_path_and_deleted_identity_fields_reject_traversal_or_empty_values() -> None:
    with pytest.raises(ValueError, match="changed_paths"):
        CodeIndexPlan(
            request=CodeIndexRequest(),
            repository_ids=(),
            changed_paths=("../outside.py",),
            deleted_paths=(),
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )
    with pytest.raises(ValueError, match="pending_paths"):
        CodeFreshnessReport(repository_ids=(), state="stale", pending_paths=("/outside.py",))
    manifest = CodeManifest(
        generation_id="generation-1",
        schema_version=CODE_PROJECTION_SCHEMA_VERSION,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
        repository_ids=("demo",),
        policy_revision="policy-1",
    )
    with pytest.raises(ValueError, match="deleted_file_ids"):
        CodeReconcilePlan(
            manifest=manifest,
            files=(),
            symbols=(),
            edges=(),
            deleted_file_ids=("",),
        )


def test_parse_result_requires_matching_source_and_parser_identity() -> None:
    file = _file()
    symbol = CodeSymbolRecord(
        symbol_id="symbol-1",
        repository_id=file.repository_id,
        file_id="file-1",
        kind="function",
        language_kind="function_definition",
        name="hello",
        qualified_name="example.hello",
        signature=None,
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=5,
        content_hash=file.content_hash,
        source_revision=file.source_revision,
        parser_spec_version="other-parser-spec",
    )
    with pytest.raises(ValueError, match="parser_spec_version"):
        CodeParseResult(file=file, symbols=(symbol,), references=())


def test_bool_fields_reject_integer_values() -> None:
    with pytest.raises(ValueError, match="enabled must be a bool"):
        CodeRepositoryEntry(
            repository_id="demo",
            root_path=Path("/tmp/demo"),
            display_name="Demo",
            enabled=1,  # type: ignore[arg-type]
            include_globs=(),
            exclude_globs=(),
            languages=(),
            state_namespace="code/demo",
            git_revision_policy="head",
            watch=False,
        )
    with pytest.raises(ValueError, match="full must be a bool"):
        CodeIndexRequest(full=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="changed must be a bool"):
        from vault_graph.code_index.code_models import CodeRepositoryMutationResponse

        CodeRepositoryMutationResponse(repository_id="demo", changed=1)  # type: ignore[arg-type]


def test_repository_add_request_validates_optional_catalog_values() -> None:
    with pytest.raises(ValueError, match="display_name"):
        CodeRepositoryAddRequest(repository_id="demo", root_path=Path("/tmp/demo"), display_name=" ")
    with pytest.raises(ValueError, match="languages"):
        CodeRepositoryAddRequest(repository_id="demo", root_path=Path("/tmp/demo"), languages=[""])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="include_globs"):
        CodeRepositoryAddRequest(repository_id="demo", root_path=Path("/tmp/demo"), include_globs=[""])  # type: ignore[arg-type]


def test_boundary_records_are_available_without_duplicate_module_types() -> None:
    assert CODE_PROJECTION_SCHEMA_VERSION == "code-projection-v1"
    assert CODE_PARSER_SPEC_VERSION
    expected = {
        CodeFileInput,
        CodeReferenceRecord,
        CodeParseDiagnostic,
        PendingCodeReference,
        CodeManifest,
        CodeReconcilePlan,
        CodeApplyResult,
        CodeSymbolQuery,
        CodeSymbolHit,
        CodeTraversalQuery,
        CodeTraversalResult,
        CodeIndexRequest,
        CodeIndexPlan,
        CodeRunReport,
        CodeFreshnessRequest,
        CodeFreshnessReport,
    }
    assert len(expected) == 16
    assert all(fields(record) for record in expected)
