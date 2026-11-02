"""결정S14: 기본 검색은 frontmatter status가 `retired`인 페이지를 결과에서 뺀다.

`deprecated` 페이지는 지금처럼 결과에 남는다. 이 변경은 VG-MOD INV-05(검색 점수·순서 유지)의
예외이며 `docs/DECISIONS.md`에 기록한다.
"""

from dataclasses import replace
from pathlib import Path

from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

REPO_ROOT = Path(__file__).resolve().parents[1]


class _StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


def _catalog(tmp_path: Path) -> VaultCatalog:
    root = tmp_path / "default"
    root.mkdir()
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )


def _service(tmp_path: Path, pages: tuple[tuple[str, dict[str, object]], ...]) -> tuple[RetrievalService, VaultCatalog]:
    """Index one chunk per page; keyword hits keep the given order (first page ranks first)."""
    catalog = _catalog(tmp_path)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    documents = []
    chunks = []
    hits = []
    for rank, (path, frontmatter) in enumerate(pages, start=1):
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


def _result_paths(service: RetrievalService, catalog: VaultCatalog, *, limit: int = 10) -> list[str]:
    response = service.search(query_text="Body", requested_scope=catalog.default_scope(), limit=limit)
    return [result.evidence[0].path for result in response.results]


def test_retired_page_is_excluded_from_default_search(tmp_path: Path) -> None:
    service, catalog = _service(
        tmp_path,
        (
            ("wiki/retired.md", {"status": "retired", "retired_reason": "no longer true", "retired_at": "2026-11-01"}),
            ("wiki/current.md", {"status": "current"}),
        ),
    )

    assert _result_paths(service, catalog) == ["wiki/current.md"]


def test_deprecated_page_still_appears_in_same_query(tmp_path: Path) -> None:
    service, catalog = _service(
        tmp_path,
        (
            ("wiki/retired.md", {"status": "retired", "retired_reason": "no longer true", "retired_at": "2026-11-01"}),
            ("wiki/deprecated.md", {"status": "deprecated", "superseded_by": "[[current]]"}),
            ("wiki/current.md", {"status": "current"}),
            ("wiki/plain.md", {}),
        ),
    )

    assert _result_paths(service, catalog) == ["wiki/deprecated.md", "wiki/current.md", "wiki/plain.md"]


def test_retired_page_does_not_take_a_limit_slot(tmp_path: Path) -> None:
    service, catalog = _service(
        tmp_path,
        (
            ("wiki/retired.md", {"status": "retired", "retired_reason": "no longer true", "retired_at": "2026-11-01"}),
            ("wiki/first.md", {"status": "current"}),
            ("wiki/second.md", {"status": "current"}),
        ),
    )

    assert _result_paths(service, catalog, limit=2) == ["wiki/first.md", "wiki/second.md"]


def test_decisions_records_inv05_exception_for_retired_filter() -> None:
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")

    entries = decisions.split("\n## ")
    matching = [entry for entry in entries if "INV-05" in entry and "`retired`" in entry]
    assert matching, "docs/DECISIONS.md must record the INV-05 exception for excluding `retired` pages"
    assert "`deprecated`" in matching[0]
