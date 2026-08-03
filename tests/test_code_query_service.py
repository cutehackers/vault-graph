from __future__ import annotations

from pathlib import Path

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
    projection = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(repository),))
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


def test_callers_stay_within_repository_and_follow_resolved_edges(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    second = service.search_symbols(CodeSymbolSearchRequest(query_text="second")).results[0]

    result = service.get_callers(CodeTraversalRequest(symbol_id=second.symbol_id, depth=2))

    assert [hit.name for hit in result.result.hits] == ["first"]
    assert result.result.direction == "inbound"
