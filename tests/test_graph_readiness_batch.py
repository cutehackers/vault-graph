"""Batch metadata evidence lookup preserves graph readiness checks."""

from dataclasses import replace
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_graph_readiness import metadata_store_with_chunk_ids
from tests.test_graph_store_contract import make_entity, make_plan
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_batch_evidence_lookup_preserves_owner_tombstone_and_hash(tmp_path: Path) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    first = make_document("default", "wiki/first.md", "first")
    second = make_document("default", "wiki/second.md", "second")
    first_chunk = make_chunk("default", first.document_id, first.path, chunk_id="first-chunk")
    second_chunk = make_chunk("default", second.document_id, second.path, chunk_id="second-chunk")
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[first, second],
        chunks=[first_chunk, second_chunk],
        tombstones=[],
    )
    keys = (
        ("default", first.document_id, first_chunk.chunk_id),
        ("default", second.document_id, second_chunk.chunk_id),
        ("default", second.document_id, first_chunk.chunk_id),
        ("other", first.document_id, first_chunk.chunk_id),
    )
    assert store.resolve_chunk_evidence_hashes(keys) == {
        keys[0]: first_chunk.content_hash,
        keys[1]: second_chunk.content_hash,
    }
    store.apply_metadata_revision(
        index_revision="metadata-2", documents=[], chunks=[], tombstones=[("default", second.path)]
    )
    assert store.resolve_chunk_evidence_hashes(keys) == {keys[0]: first_chunk.content_hash}


def test_batch_evidence_lookup_uses_one_connection_and_bounded_queries(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    chunks = [
        make_chunk("default", document.document_id, document.path, chunk_id=f"chunk-{index}") for index in range(701)
    ]
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=chunks, tombstones=[])
    keys = tuple(("default", document.document_id, chunk.chunk_id) for chunk in chunks)
    original_connect = store._connect
    connections = 0
    selections = 0

    def tracked_connect():  # type: ignore[no-untyped-def]
        nonlocal connections, selections
        connections += 1
        connection = original_connect()

        def trace(statement: str) -> None:
            nonlocal selections
            if "WITH requested" in statement:
                selections += 1

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(store, "_connect", tracked_connect)
    hashes = store.resolve_chunk_evidence_hashes(keys)

    assert len(hashes) == 701
    assert connections == 1
    assert selections == 3


def test_readiness_rechecks_mutable_metadata_and_supports_single_lookup_fakes(tmp_path: Path) -> None:
    metadata, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(tmp_path)
    graph = InMemoryGraphStore()
    graph.apply_reconcile_plan(
        make_plan(
            entities=(
                make_entity(
                    "default",
                    document_id=document_id,
                    chunk_id=chunk_id,
                    content_hash=content_hash,
                    path="wiki/page.md",
                ),
            ),
            relationships=(),
        )
    )
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))

    class SingleLookupStore:
        lookups = 0

        def __getattr__(self, name: str) -> object:
            if name == "resolve_chunk_evidence_hashes":
                raise AttributeError(name)
            return getattr(metadata, name)

        def resolve_chunk_evidence(self, *, vault_id: str, document_id: str, chunk_id: str) -> object:
            self.lookups += 1
            return metadata.resolve_chunk_evidence(vault_id=vault_id, document_id=document_id, chunk_id=chunk_id)

    fast = ReadOnlyGraphReadiness(
        metadata_store=metadata, graph_store=graph, expected_spec=current_graph_extraction_spec()
    )
    single_lookup_store = SingleLookupStore()
    fallback = ReadOnlyGraphReadiness(
        metadata_store=single_lookup_store,  # type: ignore[arg-type]
        graph_store=graph,
        expected_spec=current_graph_extraction_spec(),
    )
    assert fast.check(requested_scope=scope, actual_scopes=(scope,)) == fallback.check(
        requested_scope=scope, actual_scopes=(scope,)
    )
    with metadata.connect_for_tests() as connection:
        connection.execute("UPDATE chunks SET content_hash = 'changed' WHERE chunk_id = ?", (chunk_id,))
    changed = fast.check(requested_scope=scope, actual_scopes=(scope,))
    assert changed == fallback.check(requested_scope=scope, actual_scopes=(scope,))
    assert changed.freshness == "stale"
    assert "stale graph evidence" in changed.warnings[0]
    assert single_lookup_store.lookups == 2


def test_shared_chunk_with_different_graph_hashes_checks_each_evidence_ref(tmp_path: Path) -> None:
    metadata, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(tmp_path)
    graph = InMemoryGraphStore()
    valid = make_entity(
        "default",
        name="Valid",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    stale = make_entity(
        "default",
        name="Stale",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash="different-graph-hash",
        path="wiki/page.md",
    )
    graph.apply_reconcile_plan(make_plan(entities=(valid, stale), relationships=()))
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    report = ReadOnlyGraphReadiness(
        metadata_store=metadata,
        graph_store=graph,
        expected_spec=current_graph_extraction_spec(),
    ).check(requested_scope=scope, actual_scopes=(scope,))

    assert report.freshness == "stale"
    assert report.warnings == (f"stale graph evidence: default:{document_id}:{chunk_id}",)


@pytest.mark.parametrize(
    ("first_version", "second_version", "reverse_insertion"),
    [
        ("z-version", "a-version", False),
        ("z-version", "a-version", True),
        ("a-version", "z-version", False),
        ("a-version", "z-version", True),
    ],
)
def test_document_state_chunker_selection_matches_previous_join(
    tmp_path: Path, first_version: str, second_version: str, reverse_insertion: bool
) -> None:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    first = replace(
        make_chunk("default", document.document_id, document.path, chunk_id="a"), chunker_version=first_version
    )
    second = replace(
        make_chunk("default", document.document_id, document.path, chunk_id="z"), chunker_version=second_version
    )
    chunks = [second, first] if reverse_insertion else [first, second]
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=chunks, tombstones=[])
    with store.connect_for_tests() as connection:
        previous = connection.execute(
            """SELECT c.chunk_id, c.chunker_version FROM documents d LEFT JOIN chunks c
               ON c.vault_id = d.vault_id AND c.document_id = d.document_id
               WHERE d.vault_id = ? GROUP BY d.vault_id, d.path""",
            ("default",),
        ).fetchone()
    assert previous is not None
    assert previous["chunk_id"] == "a"
    assert store.list_document_states(("default",))[0].chunker_version == previous["chunker_version"]
