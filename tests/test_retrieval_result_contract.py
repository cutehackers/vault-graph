from dataclasses import FrozenInstanceError

import pytest

from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.errors import RetrievalContractError
from vault_graph.retrieval import (
    RetrievalResult,
    RetrievalSignal,
    RetrievalSignalKind,
    RetrievalWarning,
    StoreRevision,
    require_vector_hit_evidence_match,
    warning_for_missing_vector_evidence,
    warning_for_stale_vector,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit

SPEC = EmbeddingModelSpec(
    model_name="deterministic",
    model_version="test",
    dimensions=4,
    spec_version="embedding-spec-v1",
)


def make_evidence(vault_id: str = "default") -> EvidenceReference:
    return EvidenceReference(
        vault_id=vault_id,
        document_id=f"{vault_id}:document",
        chunk_id=f"{vault_id}:chunk",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-hash",
        metadata_index_revision="metadata-1",
        vault_revision="vault-rev-1",
    )


def make_vector_hit(vault_id: str = "default") -> VectorHit:
    return VectorHit(
        vector_id=f"{vault_id}:vector",
        vault_id=vault_id,
        document_id=f"{vault_id}:document",
        chunk_id=f"{vault_id}:chunk",
        content_scope="wiki",
        score=0.75,
        rank=1,
        embedding_spec=SPEC,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
        backend="memory-vector",
    )


def make_store_revisions() -> tuple[StoreRevision, ...]:
    return (
        StoreRevision(kind="metadata", revision="metadata-1"),
        StoreRevision(kind="vector", revision="vector-1"),
    )


def make_signal(kind: RetrievalSignalKind = "vector") -> RetrievalSignal:
    return RetrievalSignal(
        kind=kind,
        source_id=f"{kind}-1",
        rank=1,
        score=0.75,
        backend="memory-vector",
        index_revision=f"{kind}-1",
        explanation="candidate matched the query",
    )


def test_retrieval_result_requires_evidence() -> None:
    with pytest.raises(RetrievalContractError, match="evidence is required"):
        RetrievalResult(
            result_id="default:wiki/page.md:section",
            vault_id="default",
            kind="document",
            title="Page",
            summary="Body",
            rank=1,
            evidence=(),
            signals=(make_signal(),),
            relationship_status="not_applicable",
            warnings=(),
            store_revisions=make_store_revisions(),
        )


def test_vector_signal_keeps_backend_score_and_revision_off_result() -> None:
    signal = make_signal()
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(signal,),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )

    assert result.signals[0].score == 0.75
    assert result.signals[0].backend == "memory-vector"
    assert result.signals[0].index_revision == "vector-1"
    assert not hasattr(result, "score")
    assert not hasattr(result, "backend")
    assert not hasattr(result, "index_revision")


def test_graph_signal_kind_is_accepted_without_graph_runtime() -> None:
    signal = RetrievalSignal(
        kind="graph",
        source_id="edge-1",
        rank=1,
        score=1.0,
        backend="graph-store",
        index_revision="graph-1",
        explanation="relationship candidate",
    )
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(signal,),
        relationship_status="inferred",
        warnings=(),
        store_revisions=(
            StoreRevision(kind="metadata", revision="metadata-1"),
            StoreRevision(kind="graph", revision="graph-1"),
        ),
    )

    assert result.signals[0].kind == "graph"
    assert result.relationship_status == "inferred"


def test_retrieval_result_allows_cross_vault_evidence_for_relationships() -> None:
    result = RetrievalResult(
        result_id="source:target:relationship",
        vault_id="source",
        kind="relationship",
        title="Related decision",
        summary="Evidence lives in a separate Vault",
        rank=1,
        evidence=(make_evidence(vault_id="evidence"),),
        signals=(make_signal(kind="graph"),),
        relationship_status="inferred",
        warnings=(),
        store_revisions=(
            StoreRevision(kind="metadata", revision="metadata-1"),
            StoreRevision(kind="graph", revision="graph-1"),
        ),
    )

    assert result.evidence[0].vault_id == "evidence"


def test_store_revisions_are_immutable_records_not_mutable_mapping() -> None:
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(make_signal(),),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )

    assert isinstance(result.store_revisions, tuple)
    assert not hasattr(result.store_revisions, "__setitem__")
    with pytest.raises(FrozenInstanceError):
        result.store_revisions[0].__setattr__("revision", "metadata-2")


def test_store_revisions_reject_mutable_records() -> None:
    with pytest.raises(RetrievalContractError, match="store_revisions must contain StoreRevision records"):
        RetrievalResult(
            result_id="default:wiki/page.md:section",
            vault_id="default",
            kind="document",
            title="Page",
            summary="Body",
            rank=1,
            evidence=(make_evidence(),),
            signals=(make_signal(),),
            relationship_status="not_applicable",
            warnings=(),
            store_revisions=({"metadata": "metadata-1"},),  # type: ignore[arg-type]
        )


def test_vector_hit_ids_must_match_resolved_evidence_before_result() -> None:
    require_vector_hit_evidence_match(hit=make_vector_hit(), evidence=make_evidence())


def test_vector_hit_evidence_mismatch_rejects_normal_result() -> None:
    with pytest.raises(RetrievalContractError, match="vector hit ids must match evidence"):
        require_vector_hit_evidence_match(
            hit=make_vector_hit(vault_id="default"),
            evidence=make_evidence(vault_id="other"),
        )


def test_missing_vector_evidence_becomes_visible_warning() -> None:
    warning = warning_for_missing_vector_evidence(make_vector_hit())

    assert warning.code == "missing_evidence"
    assert warning.severity == "warning"


def test_vector_revision_mismatch_becomes_stale_warning() -> None:
    hit = make_vector_hit()
    evidence = make_evidence()
    stale_evidence = EvidenceReference(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256,
        metadata_index_revision="metadata-2",
        vault_revision=evidence.vault_revision,
    )

    warning = warning_for_stale_vector(hit=hit, evidence=stale_evidence)

    assert warning is not None
    assert warning.code == "stale_vector"
    assert warning.severity == "warning"


def test_vector_revision_match_has_no_stale_warning() -> None:
    assert warning_for_stale_vector(hit=make_vector_hit(), evidence=make_evidence()) is None


def test_warnings_remain_visible_on_result() -> None:
    warning = RetrievalWarning(
        code="missing_evidence",
        message="Metadata evidence could not be resolved",
        severity="warning",
    )
    result = RetrievalResult(
        result_id="default:wiki/page.md:section",
        vault_id="default",
        kind="document",
        title="Page",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(),
        relationship_status="not_applicable",
        warnings=(warning,),
        store_revisions=(StoreRevision(kind="metadata", revision="metadata-1"),),
    )

    assert result.warnings == (warning,)
