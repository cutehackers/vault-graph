from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

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
    CodeReconcilePlan,
    CodeReferenceRecord,
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

    with pytest.raises(ValueError, match="target"):
        CodeEdgeRecord(
            edge_id="edge-1",
            repository_id="demo",
            source_symbol_id="symbol-1",
            relation_kind="CALLS",
            target_symbol_id=None,
            unresolved_target_key=None,
            extraction_status="unresolved",
            anchor_start_line=1,
            anchor_start_column=0,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )


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
