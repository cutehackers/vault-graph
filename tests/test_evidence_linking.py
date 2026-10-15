from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from tests.test_app_search_readiness_service import metadata_store_with_chunk
from tests.test_graph_resource_reader import make_readiness
from vault_graph.errors import RetrievalContractError
from vault_graph.graph.graph_contracts import GraphEvidenceRef
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.vault_adapter.evidence_linking import EvidenceLinker, EvidenceSourceRevision, GraphLinksRequest


def test_forward_preserves_positions_duplicates_and_missing(tmp_path: Path) -> None:
    store, scope = metadata_store_with_chunk(tmp_path)
    chunk = store.list_chunks(scope)[0]
    key = (chunk.vault_id, chunk.document_id, chunk.chunk_id)
    missing = (chunk.vault_id, chunk.document_id, "missing")
    results = EvidenceLinker(metadata_store=store).resolve_evidence((key, missing, key))
    assert tuple(item.key for item in results) == (key, missing, key)
    assert results[0].evidence is not None
    assert results[1].evidence is None
    assert results[0] == results[2]


def test_empty_reverse_does_not_open_lookup_or_metadata(tmp_path: Path) -> None:
    store, scope = metadata_store_with_chunk(tmp_path)
    result = EvidenceLinker(metadata_store=store).find_graph_links(
        GraphLinksRequest(keys=(), actual_scopes=(scope,), include_cross_vault=False, max_keys=1, limit=1)
    )
    assert (result.coverage, result.stop_reason, result.links, result.outcomes, result.source_revisions) == (
        "complete",
        "completed",
        (),
        (),
        (),
    )


def test_unavailable_lookup_is_not_empty_success(tmp_path: Path) -> None:
    store, scope = metadata_store_with_chunk(tmp_path)
    chunk = store.list_chunks(scope)[0]
    key = (chunk.vault_id, chunk.document_id, chunk.chunk_id)
    result = EvidenceLinker(metadata_store=store).find_graph_links(
        GraphLinksRequest(keys=(key, key), actual_scopes=(scope,), include_cross_vault=False, max_keys=2, limit=1)
    )
    assert result.stop_reason == "lookup_unavailable"
    assert result.coverage == "partial"
    assert result.source_revisions == ()
    assert tuple((item.status, item.key_complete) for item in result.outcomes) == (
        ("not_processed", False),
        ("not_processed", False),
    )


@pytest.mark.parametrize("limit", [0, -1, True])
def test_invalid_limit_rejected_even_for_empty_request(tmp_path: Path, limit: int) -> None:
    store, scope = metadata_store_with_chunk(tmp_path)
    with pytest.raises(RetrievalContractError):
        EvidenceLinker(metadata_store=store).find_graph_links(
            GraphLinksRequest(keys=(), actual_scopes=(scope,), include_cross_vault=False, max_keys=1, limit=limit)
        )


def test_scope_denied_before_lookup_availability(tmp_path: Path) -> None:
    store, scope = metadata_store_with_chunk(tmp_path)
    with pytest.raises(RetrievalContractError, match="scope"):
        EvidenceLinker(metadata_store=store).find_graph_links(
            GraphLinksRequest(
                keys=(("other", "document", "chunk"),),
                actual_scopes=(scope,),
                include_cross_vault=False,
                max_keys=1,
                limit=1,
            )
        )


def linked_store(
    tmp_path: Path,
) -> tuple[SQLiteMetadataStore, QueryScope, tuple[str, str, str], tuple[EvidenceOwnerRecord, ...]]:
    store, scope = metadata_store_with_chunk(tmp_path)
    chunk = store.list_chunks(scope)[0]
    key = (chunk.vault_id, chunk.document_id, chunk.chunk_id)
    ref = GraphEvidenceRef(
        "ref-1",
        "entity",
        key[0],
        "owner-1",
        *key,
        chunk.content_hash,
        path=chunk.path,
    )
    rows = (
        EvidenceOwnerRecord(
            "entity", key[0], "owner-1", ref, "graph-1", scope_key=graph_scope_key(scope), scope_revision="graph-1"
        ),
        EvidenceOwnerRecord(
            "entity",
            key[0],
            "owner-2",
            replace(ref, evidence_ref_id="ref-2", owner_id="owner-2"),
            "graph-1",
            scope_key=graph_scope_key(scope),
            scope_revision="graph-1",
        ),
    )
    return store, scope, key, rows


class Lookup:
    def __init__(self, rows: tuple[EvidenceOwnerRecord, ...]) -> None:
        self.rows = rows
        self.calls: list[int] = []

    def lookup_evidence_owners(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
        scopes: tuple[QueryScope, ...],
        include_cross_vault: bool,
        limit: int,
    ) -> tuple[EvidenceOwnerRecord, ...]:
        self.calls.append(limit)
        return self.rows[:limit]


def test_reverse_limit_keeps_duplicates_consistent_and_marks_later_keys_unprocessed(tmp_path: Path) -> None:
    store, scope, key, rows = linked_store(tmp_path)
    lookup = Lookup(rows)
    linker = EvidenceLinker(
        metadata_store=store,
        owner_lookup=lookup,
        readiness=lambda scopes: make_readiness(scopes),
        revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
    )
    result = linker.find_graph_links(
        GraphLinksRequest(
            keys=(key, (key[0], key[1], "missing"), key),
            actual_scopes=(scope,),
            include_cross_vault=False,
            max_keys=3,
            limit=1,
        )
    )
    assert len(result.links) == 1
    assert result.coverage == "partial"
    assert result.stop_reason == "result_limit"
    assert [(item.status, item.key_complete) for item in result.outcomes] == [
        ("linked", False),
        ("not_processed", False),
        ("linked", False),
    ]
    assert lookup.calls == [2]


def test_revision_change_clears_all_data_and_provenance(tmp_path: Path) -> None:
    store, scope, key, rows = linked_store(tmp_path)
    versions = iter(((EvidenceSourceRevision("graph", "graph-1"),), (EvidenceSourceRevision("graph", "graph-2"),)))
    result = EvidenceLinker(
        metadata_store=store,
        owner_lookup=Lookup(rows),
        readiness=lambda scopes: make_readiness(scopes),
        revision_reader=lambda scopes: next(versions),
    ).find_graph_links(GraphLinksRequest((key, key), (scope,), False, 2, 10))
    assert result.stop_reason == "revision_changed"
    assert result.links == ()
    assert result.source_revisions == ()
    assert all(item.status == "not_ready" and not item.key_complete for item in result.outcomes)


@pytest.mark.parametrize(
    "corruption",
    [
        "owner",
        "vault",
        "key",
        "hash",
        "path",
        "order",
        "duplicate",
        "count",
        "scope_revision",
        "revision_type",
        "ref_type",
        "endpoint",
        "endpoint_vault",
    ],
)
def test_invalid_provider_output_is_rejected_without_details(tmp_path: Path, corruption: str) -> None:
    store, scope, key, rows = linked_store(tmp_path)
    first = rows[0]
    bad: tuple[EvidenceOwnerRecord, ...]
    if corruption == "owner":
        bad = (replace(first, owner_id="forged"),)
    elif corruption == "vault":
        bad = (replace(first, owner_vault_id="secret-vault"),)
    elif corruption == "key":
        bad = (replace(first, evidence_ref=replace(first.evidence_ref, document_id="other-document")),)
    elif corruption == "hash":
        bad = (replace(first, evidence_ref=replace(first.evidence_ref, content_hash="old")),)
    elif corruption == "path":
        bad = (replace(first, evidence_ref=replace(first.evidence_ref, path="wiki/other.md")),)
    elif corruption == "order":
        bad = tuple(reversed(rows))
    elif corruption == "duplicate":
        bad = (first, first)
    elif corruption == "scope_revision":
        bad = (replace(first, scope_revision="forged"),)
    elif corruption == "revision_type":
        bad = (replace(first, graph_revision=cast(str, 123)),)
    elif corruption == "ref_type":
        bad = (replace(first, evidence_ref=cast(GraphEvidenceRef, None)),)
    elif corruption == "endpoint":
        bad = (
            replace(
                first,
                owner_kind="relationship",
                evidence_ref=replace(first.evidence_ref, owner_kind="relationship"),
                source_vault_id=key[0],
                target_vault_id=key[0],
                source_entity_id=cast(str, 42),
                target_entity_id=cast(str, ["bad"]),
            ),
        )
    elif corruption == "endpoint_vault":
        bad = (
            replace(
                first,
                owner_kind="relationship",
                evidence_ref=replace(first.evidence_ref, owner_kind="relationship"),
                source_vault_id=key[0],
                target_vault_id=cast(str, ["bad"]),
                source_entity_id="source",
                target_entity_id="target",
            ),
        )
    else:
        bad = (first,) * 4

    class InvalidLookup(Lookup):
        def lookup_evidence_owners(self, **kwargs: object) -> tuple[EvidenceOwnerRecord, ...]:
            return bad

    with pytest.raises(RetrievalContractError, match="^invalid_lookup_result$"):
        EvidenceLinker(
            metadata_store=store,
            owner_lookup=InvalidLookup(bad),
            readiness=lambda scopes: make_readiness(scopes),
            revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
        ).find_graph_links(GraphLinksRequest((key,), (scope,), False, 1, 2))


def test_no_links_missing_and_unready_are_distinct(tmp_path: Path) -> None:
    store, scope, key, _ = linked_store(tmp_path)
    request = GraphLinksRequest((key, (key[0], key[1], "missing")), (scope,), False, 2, 10)
    lookup = Lookup(())
    linker = EvidenceLinker(
        metadata_store=store,
        owner_lookup=lookup,
        readiness=lambda scopes: make_readiness(scopes),
        revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
    )
    result = linker.find_graph_links(request)
    assert result.coverage == "complete"
    assert [(item.status, item.key_complete) for item in result.outcomes] == [
        ("no_links", True),
        ("missing_evidence", True),
    ]
    stale = EvidenceLinker(
        metadata_store=store,
        owner_lookup=lookup,
        readiness=lambda scopes: make_readiness(scopes, freshness="stale"),
        revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
    ).find_graph_links(request)
    assert stale.coverage == "partial"
    assert stale.outcomes[0].status == "not_ready"
    assert stale.source_revisions == ()


def test_all_missing_keeps_metadata_provenance_without_claiming_graph_reads(tmp_path: Path) -> None:
    store, scope, key, _ = linked_store(tmp_path)
    missing = (key[0], key[1], "missing")
    revisions = (
        EvidenceSourceRevision("metadata_fingerprint", "observed", graph_scope_key(scope)),
        EvidenceSourceRevision("graph", "graph-1", graph_scope_key(scope)),
    )
    result = EvidenceLinker(
        metadata_store=store,
        owner_lookup=Lookup(()),
        readiness=lambda scopes: make_readiness(scopes),
        revision_reader=lambda scopes: revisions,
    ).find_graph_links(GraphLinksRequest((missing,), (scope,), False, 1, 10))
    assert result.coverage == "complete"
    assert result.outcomes[0].status == "missing_evidence"
    assert result.source_revisions == revisions[:1]


@pytest.mark.parametrize("backend", ["legacy", "document"])
@pytest.mark.parametrize("cross_vault", [False, True])
def test_actual_factory_reverse_lookup_is_read_only(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    backend: str,
    cross_vault: bool,
) -> None:
    from tests.test_graph_module_public_integration import fingerprints, indexed_home
    from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
    from vault_graph.vault_scope.catalog_service import CatalogService

    vault, home = indexed_home(tmp_path, monkeypatch)
    if backend == "document":
        from typer.testing import CliRunner

        from vault_graph.cli.main import app

        switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
        assert switched.exit_code == 0, switched.output
    catalog = CatalogService(graph_home_path=home)
    scope = replace(catalog.load_catalog().default_scope(), include_cross_vault=cross_vault)
    metadata = SQLiteMetadataStore(catalog.metadata_path, initialize=False)
    keys = tuple((chunk.vault_id, chunk.document_id, chunk.chunk_id) for chunk in metadata.list_chunks(scope))
    before = fingerprints(home), fingerprints(vault)
    linker = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker()
    result = linker.find_graph_links(GraphLinksRequest(keys, (scope,), cross_vault, 100, 100))
    assert result.stop_reason == "completed"
    assert result.coverage == "complete"
    assert result.links
    assert any(row.kind == "graph_document" for row in result.source_revisions) == (backend == "document")
    assert all(link.key in keys for link in result.links)
    assert (fingerprints(home), fingerprints(vault)) == before
