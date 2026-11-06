"""Spec 2026-11-05 §4.4.13-1, A-39(검색), A-32: `include_retired`로 폐기 페이지를 찾는다.

기본 검색은 지금처럼 `retired` 페이지를 빼고, 결과 필드도 그대로다. `include_retired`가 참이면
폐기 페이지도 결과에 넣고 결과마다 `status`, `retired_reason`, `retired_at`, `superseded_by`를 붙인다.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.search_readiness import ready_report
from tests.test_mcp_tool_serialization import make_search_response
from tests.test_mcp_tools import RecordingRetrievalService, fake_factory, fake_services
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.interface.cli.main import _search_response_json, app
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_tool_serialization import search_response_to_payload
from vault_graph.interface.mcp.mcp_tools import McpToolRegistry, SearchVaultInput, parse_search_vault_input
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchResponse
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

LIFECYCLE_KEYS = ("status", "retired_reason", "retired_at", "superseded_by")
PAGES: tuple[tuple[str, dict[str, object]], ...] = (
    ("wiki/retired.md", {"status": "retired", "retired_reason": "no longer true", "retired_at": "2026-11-01"}),
    ("wiki/deprecated.md", {"status": "deprecated", "superseded_by": ["decisions/current"]}),
    ("wiki/current.md", {"status": "current"}),
    ("wiki/plain.md", {}),
)


class _StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


def _service(tmp_path: Path) -> tuple[RetrievalService, VaultCatalog]:
    root = tmp_path / "default"
    root.mkdir(parents=True)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    documents = []
    chunks = []
    hits = []
    for rank, (path, frontmatter) in enumerate(PAGES, start=1):
        document = replace(make_document("default", path, f"hash-{rank}"), frontmatter=frontmatter)
        chunk = make_chunk("default", document.document_id, document.path)
        documents.append(document)
        chunks.append(chunk)
        hits.append(
            KeywordHit(
                vault_id="default",
                document_id=document.document_id,
                chunk_id=chunk.chunk_id,
                rank=rank,
                score=-1.0,
                backend="memory-keyword",
                index_revision="metadata-1",
                matched_fields=("text",),
                provenance_family_id=document.provenance_family_id,
            )
        )
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=InMemoryKeywordIndex(tuple(hits)),
        readiness=_StaticReadiness(ready_report(vector_ok=False)),
    )
    return service, catalog


def _search(tmp_path: Path, **kwargs: Any) -> SearchResponse:
    service, catalog = _service(tmp_path)
    return service.search(query_text="Body", requested_scope=catalog.default_scope(), **kwargs)


def test_default_search_leaves_out_retired_pages_and_adds_no_lifecycle(tmp_path: Path) -> None:
    response = _search(tmp_path)

    assert [result.evidence[0].path for result in response.results] == [
        "wiki/deprecated.md",
        "wiki/current.md",
        "wiki/plain.md",
    ]
    assert all(result.lifecycle is None for result in response.results)


def test_include_retired_returns_retired_pages_with_lifecycle(tmp_path: Path) -> None:
    response = _search(tmp_path, include_retired=True)

    by_path = {result.evidence[0].path: result.lifecycle for result in response.results}
    assert list(by_path) == ["wiki/retired.md", "wiki/deprecated.md", "wiki/current.md", "wiki/plain.md"]
    retired = by_path["wiki/retired.md"]
    assert retired is not None
    assert (retired.status, retired.retired_reason, retired.retired_at, retired.superseded_by) == (
        "retired",
        "no longer true",
        "2026-11-01",
        (),
    )
    deprecated = by_path["wiki/deprecated.md"]
    assert deprecated is not None
    assert deprecated.status == "deprecated"
    assert deprecated.superseded_by == ("decisions/current",)
    plain = by_path["wiki/plain.md"]
    assert plain is not None
    assert (plain.status, plain.retired_reason, plain.retired_at, plain.superseded_by) == (None, None, None, ())


def test_mcp_and_cli_json_add_lifecycle_keys_only_with_include_retired(tmp_path: Path) -> None:
    default = _search(tmp_path / "a")
    retired = _search(tmp_path / "b", include_retired=True)

    for payload in (search_response_to_payload(default), _search_response_json(default)):
        results = cast(list[dict[str, object]], payload["results"])
        assert all(key not in result for result in results for key in LIFECYCLE_KEYS)
    for payload in (search_response_to_payload(retired), _search_response_json(retired)):
        first = cast(list[dict[str, object]], payload["results"])[0]
        assert {key: first[key] for key in LIFECYCLE_KEYS} == {
            "status": "retired",
            "retired_reason": "no longer true",
            "retired_at": "2026-11-01",
            "superseded_by": [],
        }


def test_mcp_search_vault_passes_include_retired_to_retrieval(tmp_path: Path) -> None:
    retrieval = RecordingRetrievalService(make_search_response(path="wiki/page.md"))
    registry = McpToolRegistry(
        services=fake_services(tmp_path, retrieval_service=retrieval),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    registry.search_vault(SearchVaultInput(query="GraphRAG"))
    registry.search_vault(parse_search_vault_input(query="GraphRAG", include_retired=True))

    assert [call["include_retired"] for call in retrieval.calls] == [False, True]


def test_mcp_search_vault_rejects_non_boolean_include_retired() -> None:
    with pytest.raises(McpProtocolError):
        parse_search_vault_input(query="GraphRAG", include_retired=cast(Any, "yes"))


def test_cli_search_include_retired_flag_shows_retired_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_cli_search import _unavailable_search_text_embeddings, write_page

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _unavailable_search_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _unavailable_search_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(
        vault_root,
        "wiki/old.md",
        "---\nstatus: retired\nretired_reason: replaced by the new rule\nretired_at: 2026-11-01\n---\n"
        "# Old\nGraphRAG retired rule\n",
    )
    graph_home = tmp_path / "state"
    runner = CliRunner()
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home)])

    default = runner.invoke(app, ["search", "--graph-home", str(graph_home), "--format", "json", "GraphRAG"])
    included = runner.invoke(
        app, ["search", "--graph-home", str(graph_home), "--format", "json", "--include-retired", "GraphRAG"]
    )
    text = runner.invoke(app, ["search", "--graph-home", str(graph_home), "--include-retired", "GraphRAG"])

    assert default.exit_code == 0, default.stdout
    assert json.loads(default.stdout)["result_count"] == 0
    assert included.exit_code == 0, included.stdout
    result = json.loads(included.stdout)["results"][0]
    assert result["status"] == "retired"
    assert result["retired_reason"] == "replaced by the new rule"
    assert result["retired_at"] == "2026-11-01"
    assert "status: retired (replaced by the new rule)" in text.stdout


def test_recall_and_l3_list_do_not_read_include_retired() -> None:
    """회상과 L3 목록은 검색을 거치지 않으므로 `include_retired`가 출력에 닿을 길이 없다(§4.4.13-1)."""
    import inspect

    from vault_graph.context.memory import project_memory
    from vault_graph.context.pack import recall

    for module in (recall, project_memory):
        source = inspect.getsource(module)
        assert "include_retired" not in source
        assert "retrieval_service" not in source


def test_http_search_json_has_no_lifecycle_key_without_include_retired(tmp_path: Path) -> None:
    from vault_graph.interface.http.http_serialization import domain_to_json_dict, search_response_json

    default = _search(tmp_path / "a")
    retired = _search(tmp_path / "b", include_retired=True)

    for payload in (search_response_json(default, labels={}), domain_to_json_dict(default)):
        results = cast(list[dict[str, object]], payload["results"])
        assert all("lifecycle" not in result for result in results)
    first = cast(list[dict[str, object]], search_response_json(retired, labels={})["results"])[0]
    assert first["lifecycle"] == {
        "status": "retired",
        "retired_reason": "no longer true",
        "retired_at": "2026-11-01",
        "superseded_by": [],
    }
