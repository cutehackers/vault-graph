"""Spec 2026-11-05 §10.2 원인1·2·3·4: query-time ranking rules over an unchanged index."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.candidate_ranking import (
    DOCUMENT_TAIL_CHUNKS,
    DOCUMENT_TAIL_WEIGHT,
    RANK_CONSTANT,
    document_score,
)
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchMode, SearchResponse
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


def _catalog(tmp_path: Path, vault_ids: tuple[str, ...] = ("default",)) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / f"{vault_id}-root"
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki", "raw")))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])


def _document(
    vault_id: str,
    path: str,
    *,
    content_hash: str | None = None,
    role: DocumentRole = "canonical_knowledge",
    frontmatter: dict[str, object] | None = None,
    family: str | None = None,
) -> DocumentSnapshot:
    document = make_document(vault_id, path, content_hash or f"hash:{vault_id}:{path}")
    return replace(
        document,
        source_role=role,
        frontmatter=frontmatter or {},
        provenance_family_id=family or document.provenance_family_id,
    )


def _chunk(document: DocumentSnapshot, order: int, text: str) -> ChunkSnapshot:
    return replace(
        make_chunk(
            document.vault_id, document.document_id, document.path, chunk_id=f"{document.path}#{order}", text=text
        ),
        source_role=document.source_role,
        provenance_family_id=document.provenance_family_id,
        document_order=order,
    )


def _search(
    tmp_path: Path,
    documents: list[DocumentSnapshot],
    chunks: list[ChunkSnapshot],
    query_text: str,
    *,
    mode: SearchMode = "knowledge",
    vault_ids: tuple[str, ...] = ("default",),
    limit: int = 10,
) -> SearchResponse:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    catalog = _catalog(tmp_path, vault_ids)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=SQLiteKeywordIndex(tmp_path / "metadata.sqlite3"),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )
    return service.search(
        query_text=query_text,
        requested_scope=catalog.scope_for_vault_ids(vault_ids),
        limit=limit,
        mode=mode,
    )


def _paths(response: SearchResponse) -> list[str]:
    return [f"{result.vault_id}:{result.evidence[0].path}" for result in response.results]


# 원인3: one result per document, scored by its best chunk plus a small share of the next chunks.


def test_document_score_is_best_chunk_plus_fixed_share_of_next_chunks() -> None:
    scores = (0.5, 0.25, 0.125, 0.0625)

    expected = 0.5 + DOCUMENT_TAIL_WEIGHT * sum(scores[1 : 1 + DOCUMENT_TAIL_CHUNKS])

    assert document_score(scores) == expected
    assert document_score((0.5,)) == 0.5
    assert (DOCUMENT_TAIL_WEIGHT, DOCUMENT_TAIL_CHUNKS) == (0.1, 2)


def test_chunks_of_one_document_return_as_one_result_quoting_the_best_chunk(tmp_path: Path) -> None:
    page = _document("default", "wiki/page.md")
    chunks = [
        _chunk(page, 0, "ranking ranking ranking notes"),
        _chunk(page, 1, "ranking notes with more words around it"),
        _chunk(page, 2, "ranking appears once in a long chunk of unrelated text about other matters"),
    ]

    response = _search(tmp_path, [page], chunks, "ranking")

    assert _paths(response) == ["default:wiki/page.md"]
    result = response.results[0]
    assert result.evidence[0].chunk_id == "wiki/page.md#0"
    assert [warning.code for warning in result.warnings] == ["parent_grouped"]
    assert "3 chunks" in result.warnings[0].message


def test_document_with_several_matching_chunks_passes_equal_single_chunk_document(tmp_path: Path) -> None:
    single = _document("default", "wiki/a-single.md")
    several = _document("default", "wiki/b-several.md")
    chunks = [
        _chunk(single, 0, "fusion rule"),
        _chunk(several, 0, "fusion rule"),
        _chunk(several, 1, "fusion rule"),
    ]

    response = _search(tmp_path, [single, several], chunks, "fusion rule")

    assert _paths(response) == ["default:wiki/b-several.md", "default:wiki/a-single.md"]
    assert [result.rank for result in response.results] == [1, 2]


# 원인1: knowledge mode reads source pages, ranks canonical pages first at equal relevance, skips raw evidence.


def test_knowledge_mode_returns_source_pages_after_canonical_at_equal_relevance(tmp_path: Path) -> None:
    source = _document("default", "wiki/sources/a-source.md", role="source_manifest")
    canonical = _document("default", "wiki/z-canonical.md")
    raw = _document("default", "raw/sessions/session.md", role="raw_evidence")
    chunks = [_chunk(document, 0, "harness preview") for document in (source, canonical, raw)]

    response = _search(tmp_path, [source, canonical, raw], chunks, "harness preview")

    assert _paths(response) == ["default:wiki/z-canonical.md", "default:wiki/sources/a-source.md"]


def test_explicit_modes_keep_their_role_sets(tmp_path: Path) -> None:
    source = _document("default", "wiki/sources/a-source.md", role="source_manifest")
    canonical = _document("default", "wiki/z-canonical.md")
    raw = _document("default", "raw/sessions/session.md", role="raw_evidence")
    chunks = [_chunk(document, 0, "harness preview") for document in (source, canonical, raw)]

    evidence = _search(tmp_path, [source, canonical, raw], chunks, "harness preview", mode="evidence")

    assert sorted(_paths(evidence)) == ["default:raw/sessions/session.md", "default:wiki/sources/a-source.md"]


# 원인2: only direct replacement relations collapse; pages sharing a `derived_from` source stay.


def test_pages_sharing_a_derived_from_family_are_not_collapsed(tmp_path: Path) -> None:
    family = "family:agents"
    first = _document(
        "default", "wiki/concepts/compiled.md", frontmatter={"derived_from": ["AGENTS.md"]}, family=family
    )
    second = _document(
        "default", "wiki/decisions/markdown.md", frontmatter={"derived_from": ["AGENTS.md"]}, family=family
    )
    chunks = [_chunk(first, 0, "compiled knowledge"), _chunk(second, 0, "compiled knowledge markdown")]

    response = _search(tmp_path, [first, second], chunks, "compiled knowledge")

    assert sorted(_paths(response)) == ["default:wiki/concepts/compiled.md", "default:wiki/decisions/markdown.md"]


def test_superseded_page_collapses_into_the_higher_ranked_page_of_its_chain(tmp_path: Path) -> None:
    family = "family:chain"
    new = _document("default", "wiki/decisions/new.md", frontmatter={"supersedes": "[[decisions/old]]"}, family=family)
    old = _document(
        "default", "wiki/decisions/old.md", frontmatter={"superseded_by": "wiki/decisions/new.md"}, family=family
    )
    unrelated = _document("default", "wiki/decisions/other.md")
    chunks = [
        _chunk(new, 0, "token budget token budget"),
        _chunk(old, 0, "token budget"),
        _chunk(unrelated, 0, "token budget note"),
    ]

    response = _search(tmp_path, [new, old, unrelated], chunks, "token budget")

    assert _paths(response) == ["default:wiki/decisions/new.md", "default:wiki/decisions/other.md"]


# 원인4: one ordering across the whole scope, one result for the same content in several Vaults.


def test_keyword_ranks_are_global_across_vaults(tmp_path: Path) -> None:
    weak = _document("first", "wiki/weak.md")
    strong = _document("second", "wiki/strong.md")
    chunks = [
        _chunk(weak, 0, "retrieval appears once among many other unrelated words in this long chunk"),
        _chunk(strong, 0, "retrieval retrieval retrieval"),
    ]

    response = _search(tmp_path, [weak, strong], chunks, "retrieval", vault_ids=("first", "second"))

    assert _paths(response) == ["second:wiki/strong.md", "first:wiki/weak.md"]
    assert [result.signals[0].rank for result in response.results] == [1, 2]


def test_same_content_in_two_vaults_returns_once_from_the_first_scope_vault(tmp_path: Path) -> None:
    in_first = _document("first", "wiki/copy.md", content_hash="same-content")
    in_second = _document("second", "wiki/copy.md", content_hash="same-content")
    different = _document("second", "wiki/own.md", content_hash="own-content")
    chunks = [_chunk(document, 0, "template page body") for document in (in_first, in_second, different)]

    response = _search(
        tmp_path, [in_first, in_second, different], chunks, "template page body", vault_ids=("second", "first")
    )

    assert _paths(response) == ["second:wiki/copy.md", "second:wiki/own.md"]
    duplicate = next(warning for warning in response.results[0].warnings if warning.code == "duplicate_content")
    assert duplicate.severity == "info"
    assert "first:wiki/copy.md" in duplicate.message
    assert [result.rank for result in response.results] == [1, 2]


def test_search_returns_up_to_limit_documents_when_chunks_crowd_the_candidates(tmp_path: Path) -> None:
    crowded = _document("default", "wiki/a-crowded.md")
    others = [_document("default", f"wiki/other-{index}.md") for index in range(3)]
    chunks = [_chunk(crowded, order, "needle needle needle") for order in range(30)]
    chunks += [_chunk(document, 0, "needle and a much longer tail of unrelated words here") for document in others]

    response = _search(tmp_path, [crowded, *others], chunks, "needle", limit=4)

    assert response.result_count == 4
    assert _paths(response)[0] == "default:wiki/a-crowded.md"


def test_rank_constant_is_unchanged() -> None:
    assert RANK_CONSTANT == 60.0
