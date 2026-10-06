import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from graph_document import GraphDocument, GraphLimits, ReadLimits

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from vault_graph.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.extraction.graph_source_store import PreviewGraphSourceStore
from vault_graph.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.extraction.vault_graph_document_adapter import (
    VaultDocumentMappingError,
    VaultGraphDocumentAdapter,
    VaultProjectionRequest,
)
from vault_graph.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.graph.graph_identity import stable_entity_id
from vault_graph.indexing.graph_indexer import GraphIndexer
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection.graph_projection import GraphProjectionEdge, GraphProjectionNode
from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class MemoryMetadata:
    def __init__(self, documents: tuple[DocumentSnapshot, ...], chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.documents = documents
        self.chunks = chunks

    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        return tuple(doc for doc in self.documents if doc.vault_id in scope.vault_ids)

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.vault_id == vault_id and chunk.document_id == document_id)

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.vault_id in scope.vault_ids)

    def resolve_document(self, document_id: str) -> DocumentSnapshot | None:
        return next((doc for doc in self.documents if doc.document_id == document_id), None)


def document(name: str) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id="v",
        document_id=f"doc:{name}",
        path=f"wiki/{name}.md",
        kind="wiki",
        frontmatter={"tags": [name]},
        frontmatter_hash=f"fm:{name}",
        content_hash=f"body:{name}",
        raw_sha256=f"raw:{name}",
        parser_version="parser-v1",
        last_seen_at="now",
        last_indexed_at=None,
        vault_revision="vault-1",
        index_revision="metadata-1",
    )


def chunk(doc: DocumentSnapshot, index: int, text: str) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=doc.vault_id,
        chunk_id=f"{doc.document_id}:{index}",
        document_id=doc.document_id,
        path=doc.path,
        section=f"Section {index}",
        anchor=f"section-{index}",
        text=text,
        token_count=2,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        chunker_version="chunker-v1",
        index_revision="metadata-1",
        document_order=index,
    )


def adapter(tmp_path: Path, metadata: MemoryMetadata) -> VaultGraphDocumentAdapter:
    return VaultGraphDocumentAdapter(
        metadata_store=cast(MetadataStore, metadata),
        db_path=tmp_path / "document-graph.db",
        manifest_dir=tmp_path / "manifests",
        graph_limits=GraphLimits(10, 100000, 1000000, 1000, 1000, 10000, 256),
        read_limits=ReadLimits(1000, 1000, 10000, 100, 1000000),
    )


def test_profile_change_uses_new_collection_and_preserves_old_revision(tmp_path: Path) -> None:
    source = document("source")
    metadata = MemoryMetadata((source,), (chunk(source, 0, "Body."),))
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    first = adapter(tmp_path, metadata)
    initial = first.materialize_documents(scope)
    first.sync(initial, expected_revision=0)
    original = first.restore_snapshot(collection_id=initial.collection_id)
    next_adapter = VaultGraphDocumentAdapter(
        metadata_store=cast(MetadataStore, metadata),
        db_path=tmp_path / "document-graph.db",
        manifest_dir=tmp_path / "manifests",
        graph_limits=GraphLimits(10, 100000, 1000000, 1000, 1000, 10000, 256),
        read_limits=ReadLimits(1000, 1000, 10000, 100, 1000000),
        spec=GraphExtractionSpec.from_payload(
            {
                **json.loads(current_graph_extraction_spec().serialized_spec),
                "spec_version": "graph-extraction-next",
            }
        ),
    )
    next_batch = next_adapter.materialize_documents(scope)
    assert next_batch.collection_id != initial.collection_id
    next_adapter.sync(next_batch, expected_revision=0)
    assert next_adapter.restore_snapshot(collection_id=next_batch.collection_id).graph_revision == 1
    assert first.restore_snapshot(collection_id=initial.collection_id) == original


def test_materialize_all_chunks_then_sync_and_restore(tmp_path: Path) -> None:
    source = document("source")
    metadata = MemoryMetadata((source,), (chunk(source, 0, "See [[Missing]]."), chunk(source, 1, "More content.")))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))

    batch = bridge.materialize_documents(scope)
    assert len(batch.documents) == 1
    assert len(batch.documents[0].chunks) == 2
    assert len(batch.documents[0].entity_occurrences) >= 2
    result = bridge.sync(batch, expected_revision=0)
    assert result.graph_revision == 1
    restored = bridge.restore_snapshot(collection_id=batch.collection_id, selection="all")
    assert restored.graph_revision == 1
    assert any(node.type == "WikiPage" for node in restored.nodes)
    assert any(edge.relationship_type == "mentions" for edge in restored.relationships)


def test_incremental_change_preserves_other_document_and_partial_mapping(tmp_path: Path) -> None:
    first, second = document("first"), document("second")
    metadata = MemoryMetadata(
        (first, second),
        (chunk(first, 0, "First body."), chunk(second, 0, "Second body.")),
    )
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    initial = bridge.materialize_documents(scope)
    bridge.sync(initial, expected_revision=0)
    second_id = next(
        item.document.document_id for item in initial.documents if item.source.document_id == second.document_id
    )
    before = bridge.restore_snapshot(collection_id=initial.collection_id, selection=(second_id,))

    metadata.chunks = (chunk(first, 0, "Changed first body."), chunk(second, 0, "Second body."))
    changed = bridge.materialize_documents(scope)
    result = bridge.sync(changed, expected_revision=1)
    after = bridge.restore_snapshot(collection_id=changed.collection_id, selection=(second_id,))

    assert result.graph_revision == 2
    assert result.changed_document_ids == (
        next(item.document.document_id for item in changed.documents if item.source.document_id == first.document_id),
    )
    assert before.nodes == after.nodes
    assert tuple(replace(edge, graph_index_revision="") for edge in before.relationships) == tuple(
        replace(edge, graph_index_revision="") for edge in after.relationships
    )
    assert after.graph_revision == 2


def test_explicit_full_inventory_removes_missing_document(tmp_path: Path) -> None:
    first, second = document("first"), document("second")
    metadata = MemoryMetadata((first, second), (chunk(first, 0, "First."), chunk(second, 0, "Second.")))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)
    bridge.sync(batch, expected_revision=0)
    second_id = next(
        item.document.document_id for item in batch.documents if item.source.document_id == second.document_id
    )

    incomplete = replace(batch, documents=batch.documents[:1], complete_inventory=False)
    with pytest.raises(VaultDocumentMappingError):
        bridge.sync(incomplete, expected_revision=1)
    assert bridge.restore_snapshot(collection_id=batch.collection_id).graph_revision == 1

    metadata.documents = (first,)
    metadata.chunks = (chunk(first, 0, "First."),)
    full = bridge.materialize_documents(scope)
    result = bridge.sync(full, expected_revision=1)
    assert result.removed_document_ids == (second_id,)
    assert result.graph_revision == 2
    assert all(
        node.name != "wiki/second.md" for node in bridge.restore_snapshot(collection_id=batch.collection_id).nodes
    )


def test_missing_or_corrupt_manifest_fails_closed(tmp_path: Path) -> None:
    source = document("source")
    metadata = MemoryMetadata((source,), (chunk(source, 0, "First."),))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)
    bridge.sync(batch, expected_revision=0)
    metadata.chunks = (chunk(source, 0, "Changed."),)
    changed = bridge.materialize_documents(scope)

    with patch.object(bridge, "_write_manifest", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            bridge.sync(changed, expected_revision=1)
    with pytest.raises(VaultDocumentMappingError):
        bridge.restore_snapshot(collection_id=batch.collection_id)

    recovered = bridge.recover(changed, expected_revision=2)
    assert recovered.ready and recovered.graph_revision == 2
    assert bridge.restore_snapshot(collection_id=batch.collection_id).graph_revision == 2

    path = bridge._manifest_path(batch.collection_id, 1)
    wrapped = json.loads(path.read_text(encoding="utf-8"))
    wrapped["digest"] = "0" * 64
    path.write_text(json.dumps(wrapped), encoding="utf-8")
    with pytest.raises(VaultDocumentMappingError):
        bridge._load_manifest(batch.collection_id, 1)


def test_recovery_rejects_different_source_and_finishes_pending_deletion(tmp_path: Path) -> None:
    first, second = document("first"), document("second")
    metadata = MemoryMetadata((first, second), (chunk(first, 0, "First."), chunk(second, 0, "Second.")))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    initial = bridge.materialize_documents(scope)
    bridge.sync(initial, expected_revision=0)
    metadata.documents = (first,)
    metadata.chunks = (chunk(first, 0, "Changed first."),)
    current = bridge.materialize_documents(scope)
    with patch.object(bridge, "_write_manifest", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            bridge.sync(current, expected_revision=1)
    with pytest.raises(VaultDocumentMappingError):
        bridge.restore_snapshot(collection_id=initial.collection_id)

    mismatched = replace(
        current,
        documents=(
            replace(
                current.documents[0],
                document=replace(current.documents[0].document, title="Different"),
            ),
        ),
    )
    with pytest.raises(VaultDocumentMappingError):
        bridge.recover(mismatched, expected_revision=3)
    recovered = bridge.recover(current, expected_revision=3)
    assert recovered.graph_revision == 3
    assert bridge.restore_snapshot(collection_id=initial.collection_id).graph_revision == 3


def test_empty_initial_scope_has_revision_zero_manifest(tmp_path: Path) -> None:
    metadata = MemoryMetadata((), ())
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)
    result = bridge.sync(batch, expected_revision=0)
    assert result.ready and result.graph_revision == 0
    assert not (tmp_path / "document-graph.db").exists()
    empty = bridge.restore_snapshot(collection_id=batch.collection_id)
    assert empty.graph_revision == 0
    assert empty.nodes == ()
    assert empty.relationships == ()
    assert empty.evidence_refs == ()
    with pytest.raises(VaultDocumentMappingError):
        bridge.restore_snapshot(collection_id=batch.collection_id, selection=("missing",))

    source = document("source")
    metadata.documents = (source,)
    metadata.chunks = (chunk(source, 0, "Now populated."),)
    populated = bridge.materialize_documents(scope)
    assert bridge.sync(populated, expected_revision=0).graph_revision == 1


def test_recovery_finishes_deletion_after_first_commit(tmp_path: Path) -> None:
    first, second = document("first"), document("second")
    metadata = MemoryMetadata((first, second), (chunk(first, 0, "First."), chunk(second, 0, "Second.")))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    initial = bridge.materialize_documents(scope)
    bridge.sync(initial, expected_revision=0)
    metadata.documents = (first,)
    metadata.chunks = (chunk(first, 0, "Changed first."),)
    current = bridge.materialize_documents(scope)
    with patch.object(GraphDocument, "remove_documents", side_effect=OSError("interrupted")):
        with pytest.raises(OSError):
            bridge.sync(current, expected_revision=1)
    with pytest.raises(VaultDocumentMappingError):
        bridge.restore_snapshot(collection_id=initial.collection_id)

    recovered = bridge.recover(current, expected_revision=2)
    assert recovered.graph_revision == 3
    assert len(recovered.removed_document_ids) == 1
    assert bridge.restore_snapshot(collection_id=initial.collection_id).graph_revision == 3


def test_legacy_entity_identity_is_restored(tmp_path: Path) -> None:
    source = document("source")
    metadata = MemoryMetadata((source,), (chunk(source, 0, "Body."),))
    bridge = adapter(tmp_path, metadata)
    batch = bridge.materialize_documents(QueryScope(vault_ids=("v",), content_scopes=("wiki",)))
    bridge.sync(batch, expected_revision=0)
    restored = bridge.restore_snapshot(collection_id=batch.collection_id)
    occurrence = next(item for item in batch.documents[0].entity_occurrences if item.entity_type == "WikiPage")
    expected = stable_entity_id(
        vault_id=occurrence.vault_id,
        entity_type=occurrence.entity_type,
        normalized_name=occurrence.normalized_name,
        canonical_path=occurrence.canonical_path,
    )
    assert expected in {node.entity_id for node in restored.nodes}
    assert any(ref.excerpt is not None for ref in batch.documents[0].entity_occurrences)
    assert "Body." not in next(tmp_path.joinpath("manifests").glob("*.json")).read_text(encoding="utf-8")
    projection = bridge.read_projection_input(
        VaultProjectionRequest(
            collection_id=batch.collection_id,
            selection="all",
            seed_entity_ids=(expected,),
            actual_scope_keys=("v:wiki:local",),
            max_depth=1,
            direction="out",
            relationship_types=("mentions",),
            statuses=("stated",),
            include_cross_vault=False,
            limit=10,
            edge_limit=20,
            source_graph_revisions=("graph-legacy-1",),
            relationship_revisions=tuple(
                (edge.source_vault_id, edge.relationship_id, "graph-legacy-1") for edge in restored.relationships
            ),
        )
    )
    assert projection.seeds[0].entity_id == expected
    assert projection.relationships == tuple(
        replace(edge, graph_index_revision="graph-legacy-1") for edge in restored.relationships
    )
    assert VaultGraphProjectionAdapter().project(projection).source_graph_revisions == ("graph-legacy-1",)


def test_relationship_keeps_all_legacy_evidence_refs(tmp_path: Path) -> None:
    source = replace(
        document("source"),
        frontmatter={"tags": ["source"], "title": "Shared title"},
        frontmatter_hash="fm:shared",
    )
    metadata = MemoryMetadata(
        (source,),
        (chunk(source, 0, "First section."), chunk(source, 1, "Second section.")),
    )
    bridge = adapter(tmp_path, metadata)
    batch = bridge.materialize_documents(QueryScope(vault_ids=("v",), content_scopes=("wiki",)))
    bridge.sync(batch, expected_revision=0)
    restored = bridge.restore_snapshot(collection_id=batch.collection_id)
    tag_edges = [
        edge
        for edge in restored.relationships
        if edge.relationship_type == "mentions" and len(edge.evidence_ref_ids) == 2
    ]
    assert tag_edges
    assert set(tag_edges[0].evidence_ref_ids) <= {evidence.evidence_ref_id for evidence in restored.evidence_refs}


def test_materialization_rejects_mixed_source_revisions_and_stale_batch(tmp_path: Path) -> None:
    source = document("source")
    initial_chunk = chunk(source, 0, "Body.")
    metadata = MemoryMetadata((source,), (initial_chunk,))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)

    metadata.chunks = (replace(initial_chunk, section="Changed"),)
    with pytest.raises(VaultDocumentMappingError, match="changed after materialization"):
        bridge.sync(batch, expected_revision=0)
    assert not (tmp_path / "document-graph.db").exists()

    metadata.chunks = (replace(initial_chunk, index_revision="metadata-2"),)
    with pytest.raises(VaultDocumentMappingError, match="path or revision"):
        bridge.materialize_documents(scope)


def test_materialization_rejects_incoherent_chunk_reads(tmp_path: Path) -> None:
    source = document("source")
    initial_chunk = chunk(source, 0, "Body.")

    class ChangingMetadata(MemoryMetadata):
        def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
            return (replace(initial_chunk, path="wiki/new.md"),)

    bridge = adapter(tmp_path, ChangingMetadata((source,), (initial_chunk,)))
    with pytest.raises(VaultDocumentMappingError, match="path or revision"):
        bridge.materialize_documents(QueryScope(vault_ids=("v",), content_scopes=("wiki",)))


def test_changed_location_changes_input_digest_and_unchanged_extraction_conflicts(tmp_path: Path) -> None:
    source = document("source")
    first_chunk = chunk(source, 0, "Body.")
    metadata = MemoryMetadata((source,), (first_chunk,))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    first = bridge.materialize_documents(scope)
    bridge.sync(first, expected_revision=0)

    metadata.chunks = (replace(first_chunk, section="Another section", anchor="another-section"),)
    changed = bridge.materialize_documents(scope)
    assert changed.documents[0].document.input_digest != first.documents[0].document.input_digest
    assert bridge.sync(changed, expected_revision=1).graph_revision == 2

    altered = replace(
        changed,
        documents=(
            replace(
                changed.documents[0],
                entity_occurrences=(
                    replace(changed.documents[0].entity_occurrences[0], name="Different name"),
                    *changed.documents[0].entity_occurrences[1:],
                ),
            ),
        ),
    )
    with pytest.raises(VaultDocumentMappingError, match="different legacy extraction"):
        bridge.sync(altered, expected_revision=2)
    assert bridge.restore_snapshot(collection_id=first.collection_id).graph_revision == 2


def test_empty_document_stays_in_inventory_but_not_link_context(tmp_path: Path) -> None:
    source, empty = document("source"), document("empty")
    source_chunk = chunk(source, 0, "See [[empty]].")
    metadata = MemoryMetadata((source, empty), (source_chunk,))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)
    assert len(batch.documents) == 2

    indexer = GraphIndexer(
        source_store=PreviewGraphSourceStore(chunks=(source_chunk,), documents=(source, empty)),
        graph_store=InMemoryGraphStore(),
        entity_extractor=DeterministicEntityExtractor(),
        relationship_extractor=DeterministicRelationshipExtractor(),
        graph_extraction_spec=current_graph_extraction_spec(),
        metadata_schema_version="metadata-v1",
        graph_run_id_factory=lambda: "run-1",
        graph_revision_factory=lambda: "graph-1",
    )
    plan = indexer.plan(requested_scope=scope, actual_scopes=(scope,)).reconcile_plan
    legacy_ids = {item.entity_id for item in plan.entity_upserts}
    legacy_relationship_ids = {item.relationship_id for item in plan.relationship_upserts}
    bridge.sync(batch, expected_revision=0)
    restored = bridge.restore_snapshot(collection_id=batch.collection_id)
    assert {node.entity_id for node in restored.nodes} == legacy_ids
    assert {edge.relationship_id for edge in restored.relationships} == legacy_relationship_ids


def test_manifest_file_symlink_is_rejected(tmp_path: Path) -> None:
    source = document("source")
    metadata = MemoryMetadata((source,), (chunk(source, 0, "Body."),))
    bridge = adapter(tmp_path, metadata)
    batch = bridge.materialize_documents(QueryScope(vault_ids=("v",), content_scopes=("wiki",)))
    bridge.sync(batch, expected_revision=0)
    path = bridge._manifest_path(batch.collection_id, 1)
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(VaultDocumentMappingError, match="manifest is unavailable"):
        bridge.restore_snapshot(collection_id=batch.collection_id)


def test_projection_matches_legacy_plan_including_build_and_edge_revisions(tmp_path: Path) -> None:
    source = document("source")
    source_chunk = chunk(source, 0, "See [[Missing]].")
    metadata = MemoryMetadata((source,), (source_chunk,))
    bridge = adapter(tmp_path, metadata)
    scope = QueryScope(vault_ids=("v",), content_scopes=("wiki",))
    batch = bridge.materialize_documents(scope)
    bridge.sync(batch, expected_revision=0)
    restored = bridge.restore_snapshot(collection_id=batch.collection_id)
    plan = (
        GraphIndexer(
            source_store=PreviewGraphSourceStore(chunks=(source_chunk,), documents=(source,)),
            graph_store=InMemoryGraphStore(),
            entity_extractor=DeterministicEntityExtractor(),
            relationship_extractor=DeterministicRelationshipExtractor(),
            graph_extraction_spec=current_graph_extraction_spec(),
            metadata_schema_version="metadata-v1",
            graph_run_id_factory=lambda: "run-1",
            graph_revision_factory=lambda: "graph-legacy-1",
        )
        .plan(requested_scope=scope, actual_scopes=(scope,))
        .reconcile_plan
    )
    legacy_nodes = tuple(
        GraphProjectionNode(item.vault_id, item.entity_id, item.type, item.name, item.normalized_name)
        for item in plan.entity_upserts
    )
    legacy_edges = tuple(
        GraphProjectionEdge(
            item.source_vault_id,
            item.source_entity_id,
            item.target_vault_id,
            item.target_entity_id,
            item.relationship_id,
            item.type,
            item.status,
            item.confidence,
            tuple(ref.evidence_ref_id for ref in item.evidence_refs),
            item.graph_index_revision,
        )
        for item in plan.relationship_upserts
    )
    seed = next(node for node in legacy_nodes if node.type == "WikiPage")
    request = VaultProjectionRequest(
        collection_id=batch.collection_id,
        selection="all",
        seed_entity_ids=(seed.entity_id,),
        actual_scope_keys=(plan.graph_revision_rows[0].actual_scope,),
        max_depth=1,
        direction="out",
        relationship_types=("mentions",),
        statuses=("stated",),
        include_cross_vault=False,
        limit=10,
        edge_limit=20,
        source_graph_revisions=tuple(row.graph_index_revision for row in plan.graph_revision_rows),
        relationship_revisions=tuple(
            (edge.source_vault_id, edge.relationship_id, edge.graph_index_revision) for edge in legacy_edges
        ),
    )
    shadow_input = bridge.read_projection_input(request)
    legacy_input = replace(shadow_input, nodes=legacy_nodes, relationships=legacy_edges, seeds=(seed,))
    assert {node.entity_id for node in restored.nodes} == {node.entity_id for node in legacy_nodes}
    assert {edge.relationship_id for edge in restored.relationships} == {edge.relationship_id for edge in legacy_edges}
    assert VaultGraphProjectionAdapter().project(shadow_input) == VaultGraphProjectionAdapter().project(legacy_input)
