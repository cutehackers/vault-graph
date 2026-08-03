from __future__ import annotations

from pathlib import Path

from vault_graph.code_index.code_models import (
    CodeIndexRequest,
    CodeRepositoryEntry,
    CodeSymbolRequest,
    CodeSymbolSearchRequest,
)
from vault_graph.code_index.code_projection_service import CodeProjectionService


def test_querying_live_source_does_not_mutate_repository_or_projection(tmp_path: Path) -> None:
    from vault_graph.code_index.code_query_service import CodeQueryService
    from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "sample.py"
    source.write_text("def example():\n    return 1\n", encoding="utf-8")
    state = tmp_path / "state"
    entry = CodeRepositoryEntry(
        repository_id="demo",
        root_path=repository,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="content-hash",
        watch=False,
    )
    projection = CodeProjectionService.for_testing(state_path=state, entries=(entry,))
    projection.apply(CodeIndexRequest(full=True))
    active = projection.generation_manager.active_layout(())
    assert active is not None
    database = active.database_path
    source_before = source.read_bytes()
    database_before = database.read_bytes()
    service = CodeQueryService(
        catalog=(entry,),
        store=SQLiteCodeProjectionStore.open_read_only(database),
        freshness_service=projection,
    )
    symbol = service.search_symbols(CodeSymbolSearchRequest("example")).results[0]

    response = service.get_symbol(CodeSymbolRequest(symbol.symbol_id, include_source=True))

    assert response.source_lines == ("def example():", "    return 1")
    assert source.read_bytes() == source_before
    assert database.read_bytes() == database_before


def test_changed_source_keeps_only_a_safe_relative_path_attribution(tmp_path: Path) -> None:
    from vault_graph.code_index.code_query_service import CodeQueryService
    from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "sample.py"
    source.write_text("def example():\n    return 1\n", encoding="utf-8")
    state = tmp_path / "state"
    entry = CodeRepositoryEntry(
        repository_id="demo",
        root_path=repository,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="content-hash",
        watch=False,
    )
    projection = CodeProjectionService.for_testing(state_path=state, entries=(entry,))
    projection.apply(CodeIndexRequest(full=True))
    active = projection.generation_manager.active_layout(())
    assert active is not None
    service = CodeQueryService(
        catalog=(entry,),
        store=SQLiteCodeProjectionStore.open_read_only(active.database_path),
        freshness_service=projection,
    )
    symbol = service.search_symbols(CodeSymbolSearchRequest("example")).results[0]
    source.write_text("def example():\n    return 2\n", encoding="utf-8")

    response = service.get_symbol(CodeSymbolRequest(symbol.symbol_id, include_source=True))

    assert response.source_uri is None
    assert response.source_relative_path == "sample.py"
    assert "source_changed_since_index" in response.warnings
    assert str(repository) not in "\n".join(response.warnings)


def test_unavailable_source_keeps_only_a_safe_relative_path_attribution(tmp_path: Path) -> None:
    from vault_graph.code_index.code_query_service import CodeQueryService
    from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore

    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "sample.py"
    source.write_text("def example():\n    return 1\n", encoding="utf-8")
    state = tmp_path / "state"
    entry = CodeRepositoryEntry(
        repository_id="demo",
        root_path=repository,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="content-hash",
        watch=False,
    )
    projection = CodeProjectionService.for_testing(state_path=state, entries=(entry,))
    projection.apply(CodeIndexRequest(full=True))
    active = projection.generation_manager.active_layout(())
    assert active is not None
    service = CodeQueryService(
        catalog=(entry,),
        store=SQLiteCodeProjectionStore.open_read_only(active.database_path),
        freshness_service=projection,
    )
    symbol = service.search_symbols(CodeSymbolSearchRequest("example")).results[0]
    source.unlink()

    response = service.get_symbol(CodeSymbolRequest(symbol.symbol_id, include_source=True))

    assert response.source_uri is None
    assert response.source_relative_path == "sample.py"
    assert "source_unavailable" in response.warnings
    assert str(repository) not in "\n".join(response.warnings)
