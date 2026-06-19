from __future__ import annotations

import pytest

from vault_graph.errors import ResultExplanationError
from vault_graph.memory.result_explanation import (
    CachedExplanationView,
    ExplainResultService,
    ExplanationEvidenceRef,
    ExplanationRecord,
    ExplanationSignal,
    ExplanationWarning,
    explanation_record_to_dict,
)


def make_evidence_ref() -> ExplanationEvidenceRef:
    return ExplanationEvidenceRef(
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-hash",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )


def make_signal() -> ExplanationSignal:
    return ExplanationSignal(
        kind="keyword",
        source_id="candidate-1",
        rank=1,
        score=0.75,
        backend="sqlite-fts5",
        index_revision="keyword-1",
        explanation="candidate matched query terms",
    )


def make_warning() -> ExplanationWarning:
    return ExplanationWarning(
        code="stale_vector",
        message="Vector result used stale metadata",
        severity="warning",
        affected_vault_ids=("main",),
        recovery_hint="Run vg index --vector.",
    )


def make_record(result_id: str = "main:chunk-1") -> ExplanationRecord:
    return ExplanationRecord(
        result_id=result_id,
        source_kind="search_result",
        title="wiki/page.md#Section",
        summary="Body",
        vault_id="main",
        evidence=(make_evidence_ref(),),
        signals=(make_signal(),),
        relationship_status="not_applicable",
        store_revisions=({"kind": "metadata", "revision": "metadata-1"},),
        warnings=(make_warning(),),
        resource_links=({"rel": "evidence", "uri": "vault://main/documents/wiki%2Fpage.md"},),
        generated_at="2026-06-19T00:00:00+00:00",
    )


class MissingCache:
    def get(self, result_id: str) -> CachedExplanationView | None:
        del result_id
        return None


class CacheHit:
    def __init__(self, record: ExplanationRecord) -> None:
        self.record = record
        self.cached_at = "2026-06-19T00:00:01+00:00"


class HitCache:
    def __init__(self, record: ExplanationRecord) -> None:
        self._record = record

    def get(self, result_id: str) -> CacheHit | None:
        if result_id == self._record.result_id:
            return CacheHit(self._record)
        return None


def test_explanation_record_requires_identity_and_evidence() -> None:
    with pytest.raises(ResultExplanationError, match="result_id is required"):
        make_record(result_id="")

    with pytest.raises(ResultExplanationError, match="evidence is required"):
        ExplanationRecord(
            result_id="main:chunk-1",
            source_kind="search_result",
            title="wiki/page.md#Section",
            summary="Body",
            vault_id="main",
            evidence=(),
            signals=(make_signal(),),
            relationship_status="not_applicable",
            store_revisions=({"kind": "metadata", "revision": "metadata-1"},),
            warnings=(),
            resource_links=({"rel": "evidence", "uri": "vault://main/documents/wiki%2Fpage.md"},),
            generated_at="2026-06-19T00:00:00+00:00",
        )


def test_explanation_warning_requires_affected_vault_ids() -> None:
    with pytest.raises(ResultExplanationError, match="affected_vault_ids is required"):
        ExplanationWarning(
            code="stale_vector",
            message="Vector result used stale metadata",
            severity="warning",
            affected_vault_ids=(),
        )


def test_explain_result_service_rejects_blank_result_id() -> None:
    service = ExplainResultService(cache=MissingCache())

    with pytest.raises(ResultExplanationError, match="invalid_result_id: result_id is required"):
        service.explain(result_id=" ")


def test_explain_result_service_reports_missing_result_id() -> None:
    service = ExplainResultService(cache=MissingCache())

    with pytest.raises(ResultExplanationError, match="result_explanation_not_found"):
        service.explain(result_id="missing")


def test_explain_result_service_returns_cached_record() -> None:
    record = make_record()
    service = ExplainResultService(cache=HitCache(record))

    assert service.explain(result_id=record.result_id) == record


def test_explanation_record_to_dict_is_json_safe() -> None:
    payload = explanation_record_to_dict(make_record())

    assert payload == {
        "result_id": "main:chunk-1",
        "source_kind": "search_result",
        "title": "wiki/page.md#Section",
        "summary": "Body",
        "vault_id": "main",
        "evidence": [
            {
                "vault_id": "main",
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "path": "wiki/page.md",
                "section": "Section",
                "anchor": "section",
                "content_hash": "chunk-hash",
                "raw_sha256": "raw-hash",
                "metadata_index_revision": "metadata-1",
                "vault_revision": "vault-1",
            }
        ],
        "signals": [
            {
                "kind": "keyword",
                "source_id": "candidate-1",
                "rank": 1,
                "score": 0.75,
                "backend": "sqlite-fts5",
                "index_revision": "keyword-1",
                "explanation": "candidate matched query terms",
            }
        ],
        "relationship_status": "not_applicable",
        "store_revisions": [{"kind": "metadata", "revision": "metadata-1"}],
        "warnings": [
            {
                "code": "stale_vector",
                "message": "Vector result used stale metadata",
                "severity": "warning",
                "affected_vault_ids": ["main"],
                "recovery_hint": "Run vg index --vector.",
            }
        ],
        "resource_links": [{"rel": "evidence", "uri": "vault://main/documents/wiki%2Fpage.md"}],
        "generated_at": "2026-06-19T00:00:00+00:00",
    }
