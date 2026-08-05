from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from vault_graph.code_index.code_freshness import CodeFreshnessService
from vault_graph.code_index.code_models import (
    CodeFileOutlineRequest,
    CodeIndexRequest,
    CodeRepositoryEntry,
    CodeSymbolRequest,
    CodeSymbolSearchRequest,
    CodeTraversalRequest,
)
from vault_graph.code_index.code_projection_service import CodeProjectionService
from vault_graph.code_index.code_query_service import CodeQueryService
from vault_graph.code_index.source_scanning import CodeSourceScanner
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore


def _entry(root: Path) -> CodeRepositoryEntry:
    return CodeRepositoryEntry(
        repository_id="demo",
        root_path=root,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="content-hash",
        watch=False,
    )


def _service(tmp_path: Path) -> tuple[CodeQueryService, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "sample.py").write_text(
        "def first():\n    return second()\n\ndef second():\n    return 2\n",
        encoding="utf-8",
    )
    projection = CodeProjectionService.for_testing(graph_home_path=tmp_path / "state", entries=(_entry(repository),))
    projection.apply(CodeIndexRequest(full=True))
    active = projection.generation_manager.active_layout(())
    assert active is not None
    from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

    store = SQLiteCodeProjectionStore.open_read_only(active.database_path)
    return CodeQueryService(catalog=(_entry(repository),), store=store, freshness_service=projection), repository


def test_search_and_outline_are_repository_scoped_and_stably_ordered(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    search = service.search_symbols(CodeSymbolSearchRequest(query_text="second", repository_ids=("demo",)))
    outline = service.get_file_outline(CodeFileOutlineRequest(repository_id="demo", relative_path="sample.py"))

    assert [hit.name for hit in search.results] == ["second"]
    assert [symbol.name for symbol in outline.symbols] == ["first", "sample", "second"]
    assert outline.freshness == "fresh"


def test_symbol_source_is_live_bounded_evidence_with_a_safe_uri(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    hit = service.search_symbols(CodeSymbolSearchRequest(query_text="first")).results[0]

    result = service.get_symbol(CodeSymbolRequest(symbol_id=hit.symbol_id, include_source=True, max_lines=2))

    assert result.symbol is not None
    assert result.source_uri == "vg-source://demo/sample.py#L1-L2"
    assert result.source_lines == ("def first():", "    return second()")


def test_unscoped_symbol_name_resolves_in_a_single_registered_repository(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    result = service.get_symbol(CodeSymbolRequest("first"))

    assert result.symbol is not None
    assert result.symbol.name == "first"


def test_query_reads_persisted_status_without_scanning_the_repository(tmp_path: Path) -> None:
    from vault_graph.code_index.code_freshness import CodeFreshnessService
    from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "sample.py").write_text("def example():\n    return 1\n", encoding="utf-8")
    entry = _entry(repository)
    projection = CodeProjectionService.for_testing(graph_home_path=tmp_path / "state", entries=(entry,))
    projection.apply(CodeIndexRequest(full=True))
    active = projection.generation_manager.active_layout(())
    assert active is not None

    class Scanner:
        parser_spec_version = "unused"

        def scan(self, _entry: CodeRepositoryEntry) -> None:
            raise AssertionError("query must not scan source files")

    service = CodeQueryService(
        catalog=(entry,),
        store=SQLiteCodeProjectionStore.open_read_only(active.database_path),
        freshness_service=CodeFreshnessService(
            catalog=(entry,),
            scanner=cast(CodeSourceScanner, Scanner()),
            generation_manager=projection.generation_manager,
        ),
    )

    response = service.search_symbols(CodeSymbolSearchRequest("example"))

    assert response.results
    assert response.freshness == "unknown"
    assert "live source verification was not requested" in response.warnings


def test_callers_stay_within_repository_and_follow_resolved_edges(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    second = service.search_symbols(CodeSymbolSearchRequest(query_text="second")).results[0]

    result = service.get_callers(CodeTraversalRequest(symbol_id=second.symbol_id, depth=2, include_uncertain=True))

    assert [hit.name for hit in result.result.hits] == ["first"]
    assert result.result.direction == "inbound"


def test_scoped_query_rejects_direct_ids_and_outlines_outside_its_repository(tmp_path: Path) -> None:
    from vault_graph.code_index.code_models import CodeFreshnessReport, CodeSymbolRecord

    repository_a = tmp_path / "repository-a"
    repository_b = tmp_path / "repository-b"
    repository_a.mkdir()
    repository_b.mkdir()
    entry_a = _entry(repository_a)
    entry_b = replace(entry_a, repository_id="other", root_path=repository_b, state_namespace="code/other")
    foreign = CodeSymbolRecord(
        symbol_id="foreign-symbol",
        repository_id="other",
        file_id="foreign-file",
        kind="function",
        language_kind="function_definition",
        name="foreign",
        qualified_name="foreign",
        signature=None,
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=1,
        content_hash="0" * 64,
        source_revision="content-hash:foreign",
        parser_spec_version="parser-v1",
    )

    class Store:
        def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None:
            return foreign if symbol_id == foreign.symbol_id else None

    class Freshness:
        def status(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
            return CodeFreshnessReport(repository_ids=repository_ids, state="fresh")

    service = CodeQueryService(
        catalog=(entry_a, entry_b),
        store=cast(CodeProjectionStore, Store()),
        freshness_service=cast(CodeFreshnessService | CodeProjectionService, Freshness()),
        repository_ids=("demo",),
    )

    direct = service.get_symbol(CodeSymbolRequest("foreign-symbol"))

    assert direct.symbol is None
    assert "symbol_scope_mismatch" in direct.warnings
    with pytest.raises(ValueError, match="outside the query service scope"):
        service.get_file_outline(CodeFileOutlineRequest(repository_id="other", relative_path="sample.py"))


def test_unscoped_name_reports_ambiguity_across_registered_repositories(tmp_path: Path) -> None:
    from vault_graph.code_index.code_models import CodeFreshnessReport, CodeSymbolRecord

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _entry(first_root)
    second = replace(first, repository_id="other", root_path=second_root, state_namespace="code/other")
    first_symbol = CodeSymbolRecord(
        symbol_id="first-symbol",
        repository_id="demo",
        file_id="first-file",
        kind="function",
        language_kind="function_definition",
        name="shared",
        qualified_name="shared",
        signature=None,
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=1,
        content_hash="1" * 64,
        source_revision="content-hash:first",
        parser_spec_version="parser-v1",
    )
    second_symbol = replace(first_symbol, symbol_id="second-symbol", repository_id="other", file_id="second-file")

    class Store:
        def get_symbol(self, symbol_id: str) -> None:
            return None

        def symbols(self, repository_ids: tuple[str, ...]) -> tuple[CodeSymbolRecord, ...]:
            assert repository_ids == ("demo", "other")
            return first_symbol, second_symbol

    class Freshness:
        def status(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
            return CodeFreshnessReport(repository_ids=repository_ids, state="fresh")

    service = CodeQueryService(
        catalog=(first, second),
        store=cast(CodeProjectionStore, Store()),
        freshness_service=cast(CodeFreshnessService | CodeProjectionService, Freshness()),
    )

    result = service.get_symbol(CodeSymbolRequest("shared"))

    assert result.symbol is None
    assert "ambiguous_symbol" in result.warnings


def test_aggregate_query_excludes_projection_records_outside_the_registered_catalog(tmp_path: Path) -> None:
    from vault_graph.code_index.code_models import CodeFreshnessReport, CodeSymbolHit, CodeSymbolQuery, CodeSymbolRecord

    repository = tmp_path / "repository"
    repository.mkdir()
    entry = _entry(repository)
    stale = CodeSymbolRecord(
        symbol_id="stale-symbol",
        repository_id="removed-repository",
        file_id="stale-file",
        kind="function",
        language_kind="function_definition",
        name="stale",
        qualified_name="stale",
        signature=None,
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=1,
        content_hash="2" * 64,
        source_revision="content-hash:stale",
        parser_spec_version="parser-v1",
    )

    class Store:
        def search_symbols(self, query: CodeSymbolQuery) -> tuple[CodeSymbolHit, ...]:
            assert query.repository_ids == ("demo",)
            return ()

        def get_symbol(self, symbol_id: str) -> CodeSymbolRecord | None:
            return stale if symbol_id == stale.symbol_id else None

    class Freshness:
        def status(self, repository_ids: tuple[str, ...]) -> CodeFreshnessReport:
            return CodeFreshnessReport(repository_ids=repository_ids, state="fresh")

    service = CodeQueryService(
        catalog=(entry,),
        store=cast(CodeProjectionStore, Store()),
        freshness_service=cast(CodeFreshnessService | CodeProjectionService, Freshness()),
    )

    search = service.search_symbols(CodeSymbolSearchRequest("stale"))
    direct = service.get_symbol(CodeSymbolRequest("stale-symbol"))

    assert search.results == ()
    assert direct.symbol is None
    assert "symbol_scope_mismatch" in direct.warnings
