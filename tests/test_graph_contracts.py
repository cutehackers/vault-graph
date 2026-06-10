from dataclasses import FrozenInstanceError

import pytest

from vault_graph.errors import GraphRecordInvalid
from vault_graph.graph.graph_contracts import (
    GraphEvidenceRef,
    GraphExtractionSpec,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import (
    stable_entity_id,
    stable_evidence_ref_id,
    stable_relationship_id,
)


def test_current_graph_extraction_spec_has_canonical_digest() -> None:
    spec = current_graph_extraction_spec()

    assert spec.spec_version == "graph-extraction-spec-v1"
    assert len(spec.spec_digest) == 64
    assert spec.spec_digest == GraphExtractionSpec.from_payload(spec.payload()).spec_digest


def test_entity_id_is_stable_and_vault_scoped() -> None:
    first = stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )
    second = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )

    assert first == stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="graphrag",
        canonical_path="wiki/graphrag.md",
    )
    assert first != second


def test_relationship_id_includes_source_and_target_vaults() -> None:
    left = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id="first",
        source_entity_id="source",
        target_vault_id="second",
        target_entity_id="target",
    )
    reversed_edge = stable_relationship_id(
        relationship_type="depends_on",
        source_vault_id="second",
        source_entity_id="target",
        target_vault_id="first",
        target_entity_id="source",
    )

    assert left != reversed_edge


def test_evidence_ref_requires_owner_and_evidence_vault_identity() -> None:
    evidence_ref_id = stable_evidence_ref_id(
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id="rel-1",
        evidence_vault_id="second",
        document_id="doc-1",
        chunk_id="chunk-1",
        anchor="decision",
    )
    ref = GraphEvidenceRef(
        evidence_ref_id=evidence_ref_id,
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id="rel-1",
        evidence_vault_id="second",
        document_id="doc-1",
        chunk_id="chunk-1",
        content_hash="chunk-hash",
        section="Decision",
        anchor="decision",
        path="wiki/decision.md",
        excerpt="rendering hint",
    )

    assert ref.evidence_ref_id == evidence_ref_id
    assert ref.owner_kind == "relationship"
    assert ref.evidence_vault_id == "second"


def test_invalid_relationship_status_is_rejected() -> None:
    evidence = GraphEvidenceRef(
        evidence_ref_id="evidence",
        owner_kind="relationship",
        owner_vault_id="default",
        owner_id="rel",
        evidence_vault_id="default",
        document_id="doc",
        chunk_id="chunk",
        content_hash="chunk-hash",
        section=None,
        anchor=None,
        path="wiki/page.md",
        excerpt=None,
    )

    with pytest.raises(GraphRecordInvalid, match="unsupported relationship status"):
        RelationshipRecord(
            relationship_id="rel",
            type="depends_on",
            source_vault_id="default",
            source_entity_id="source",
            target_vault_id="default",
            target_entity_id="target",
            evidence_refs=(evidence,),
            status="confirmed",
            confidence=0.8,
            extraction_method="test",
            graph_extraction_spec_version="graph-extraction-spec-v1",
            graph_extraction_spec_digest="0" * 64,
            created_at="2026-06-10T00:00:00+00:00",
            updated_at="2026-06-10T00:00:00+00:00",
            graph_index_revision="graph-1",
        )


def test_graph_records_are_immutable() -> None:
    spec = current_graph_extraction_spec()

    with pytest.raises(FrozenInstanceError):
        spec.__setattr__("spec_version", "changed")
