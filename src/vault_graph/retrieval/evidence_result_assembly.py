from __future__ import annotations

import re

from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.retrieval.candidate_ranking import FusedCandidate, rank_resolved_candidates
from vault_graph.retrieval.retrieval_result import RetrievalResult, StoreRevision
from vault_graph.retrieval.search_response import SearchMode, SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore
from vault_graph.vault_adapter.evidence_linking import EvidenceLinker


class EvidenceResultAssembly:
    def __init__(self, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store
        self._evidence_linker = EvidenceLinker(metadata_store=metadata_store)

    def resolve_results(
        self,
        *,
        candidates: tuple[FusedCandidate, ...],
        mode: SearchMode,
        allowed_roles: tuple[DocumentRole, ...],
    ) -> tuple[tuple[RetrievalResult, ...], int, tuple[SearchWarning, ...]]:
        dropped = 0
        warnings: list[SearchWarning] = []
        resolved: list[tuple[FusedCandidate, EvidenceReference, str]] = []
        for candidate in candidates:
            evidence = self._evidence_linker.resolve_evidence(
                ((candidate.vault_id, candidate.document_id, candidate.chunk_id),)
            )[0].evidence
            chunk = self._metadata_store.resolve_chunk(vault_id=candidate.vault_id, chunk_id=candidate.chunk_id)
            if evidence is None or chunk is None:
                dropped += 1
                warnings.append(
                    SearchWarning(
                        code="missing_evidence",
                        message=f"Metadata evidence could not be resolved for search candidate: {candidate.chunk_id}",
                        severity="warning",
                        affected_vault_ids=(candidate.vault_id,),
                        document_id=candidate.document_id,
                        chunk_id=candidate.chunk_id,
                    )
                )
                continue
            if evidence.source_role not in allowed_roles:
                continue
            resolved.append((candidate, evidence, _excerpt(chunk.text)))

        ranked = rank_resolved_candidates(resolved, mode=mode)
        results = tuple(
            self._result_for_candidate(candidate=candidate, evidence=evidence, summary=summary, rank=rank)
            for rank, (candidate, evidence, summary) in enumerate(ranked, start=1)
        )
        return results, dropped, tuple(warnings)

    def _result_for_candidate(
        self, *, candidate: FusedCandidate, evidence: EvidenceReference, summary: str, rank: int
    ) -> RetrievalResult:
        family_id = evidence.provenance_family_id or evidence.document_id
        family_reader = getattr(self._metadata_store, "list_family_evidence", None)
        family = (
            family_reader(vault_id=evidence.vault_id, provenance_family_id=family_id) if callable(family_reader) else ()
        )
        supporting = _one_reference_per_document(
            tuple(item for item in family if item.source_role in ("source_manifest", "raw_evidence"))
        )
        audit = _one_reference_per_document(
            tuple(item for item in family if item.source_role in ("generated_view", "operation_log", "audit_record"))
        )
        return RetrievalResult(
            result_id=f"{candidate.vault_id}:{candidate.chunk_id}:rank-{rank}",
            vault_id=candidate.vault_id,
            kind="evidence_chunk",
            title=_title_for_evidence(evidence),
            summary=summary,
            rank=rank,
            evidence=(evidence,),
            signals=candidate.signals,
            relationship_status="not_applicable",
            warnings=(),
            store_revisions=_result_store_revisions(candidate=candidate, evidence=evidence),
            provenance_family_id=family_id,
            supporting_evidence=supporting,
            audit_records=audit,
        )


def _one_reference_per_document(evidence: tuple[EvidenceReference, ...]) -> tuple[EvidenceReference, ...]:
    by_document: dict[tuple[str, str], EvidenceReference] = {}
    for item in evidence:
        by_document.setdefault((item.vault_id, item.document_id), item)
    return tuple(by_document.values())


def _result_store_revisions(*, candidate: FusedCandidate, evidence: EvidenceReference) -> tuple[StoreRevision, ...]:
    revisions = []
    if evidence.metadata_index_revision:
        revisions.append(StoreRevision(kind="metadata", revision=evidence.metadata_index_revision))
    for signal in candidate.signals:
        revisions.append(StoreRevision(kind=signal.kind, revision=signal.index_revision))
    return tuple(dict.fromkeys(revisions))


def _title_for_evidence(evidence: EvidenceReference) -> str:
    if evidence.anchor:
        return f"{evidence.path}#{evidence.anchor}"
    if evidence.section:
        return f"{evidence.path}#{evidence.section}"
    return evidence.path


def _excerpt(text: str, *, max_length: int = 240) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3].rstrip()}..."
