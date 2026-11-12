"""Spec 2026-11-11 §4.2.6: the narrow metadata reads give what the whole-document reads gave."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.indexing.ingestion.document_snapshots import ChunkKind, DocumentRole
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.search.context_expansion import ContextExpander
from vault_graph.retrieval.search.evidence_result_assembly import _one_reference_per_document
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FAMILY = "family:session"
SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki", "raw"))


class WholeDocumentStore:
    """The same store without the narrow reads, so readers take the whole-document path."""

    def __init__(self, store: SQLiteMetadataStore) -> None:
        self._store = store

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        return self._store.list_document_chunks(vault_id=vault_id, document_id=document_id)


def _document(path: str, role: DocumentRole) -> DocumentSnapshot:
    return replace(make_document("default", path, f"hash:{path}"), source_role=role, provenance_family_id=FAMILY)


def _chunks(document: DocumentSnapshot, kinds: tuple[ChunkKind, ...]) -> list[ChunkSnapshot]:
    # Orders repeat on purpose (2 and 2), so ties break on chunk_id as in the whole-document sort.
    orders = (0, 1, 2, 2, 3, 4, 5, 6)
    return [
        replace(
            make_chunk("default", document.document_id, document.path, chunk_id=f"{document.path}#{index}"),
            source_role=document.source_role,
            provenance_family_id=FAMILY,
            document_order=orders[index],
            chunk_kind=kind,
            token_count=10,
        )
        for index, kind in enumerate(kinds)
    ]


@pytest.fixture
def store(tmp_path: Path) -> SQLiteMetadataStore:
    page = _document("wiki/page.md", "canonical_knowledge")
    session = _document("raw/sessions/one.md", "raw_evidence")
    source = _document("wiki/sources/one.md", "source_manifest")
    chunks = [
        *_chunks(page, ("page_card", "body", "body", "body", "template", "body", "body")),
        *_chunks(session, ("body",) * 8),
        *_chunks(source, ("page_card", "body")),
    ]
    metadata = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    metadata.apply_metadata_revision(
        index_revision="metadata-1", documents=[page, session, source], chunks=chunks, tombstones=[]
    )
    return metadata


@pytest.mark.parametrize("radius", [0, 1, 2])
def test_window_expansion_matches_whole_document_expansion(store: SQLiteMetadataStore, radius: int) -> None:
    narrow = ContextExpander(metadata_store=store)
    whole = ContextExpander(metadata_store=WholeDocumentStore(store))  # type: ignore[arg-type]

    for path in ("wiki/page.md", "raw/sessions/one.md"):
        for chunk in store.list_document_chunks(vault_id="default", document_id=f"default:{path}"):
            kwargs = {"matched_chunk": chunk, "scope": SCOPE, "max_tokens": 1000, "neighbor_radius": radius}
            assert narrow.expand(**kwargs) == whole.expand(**kwargs), (path, chunk.chunk_id)  # type: ignore[arg-type]


def test_window_of_a_missing_chunk_is_empty(store: SQLiteMetadataStore) -> None:
    assert (
        store.list_document_chunk_window(
            vault_id="default", document_id="default:wiki/page.md", chunk_id="missing", radius=1
        )
        == ()
    )


def test_family_document_evidence_keeps_the_first_reference_of_each_document(store: SQLiteMetadataStore) -> None:
    every = store.list_family_evidence(vault_id="default", provenance_family_id=FAMILY)
    first = store.list_family_document_evidence(vault_id="default", provenance_family_id=FAMILY)

    for roles in (("source_manifest", "raw_evidence"), ("canonical_knowledge",)):
        assert _one_reference_per_document(tuple(item for item in every if item.source_role in roles)) == (
            _one_reference_per_document(tuple(item for item in first if item.source_role in roles))
        )
    assert len(first) == 3
