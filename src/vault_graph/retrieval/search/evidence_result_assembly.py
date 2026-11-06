from __future__ import annotations

import re
from dataclasses import dataclass, replace

from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker
from vault_graph.retrieval.search.candidate_ranking import FusedCandidate, rank_resolved_candidates
from vault_graph.retrieval.search.retrieval_result import RetrievalResult, RetrievalWarning, StoreRevision
from vault_graph.retrieval.search.search_response import SearchMode, SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

RETIRED_STATUS = "retired"
PARENT_GROUPED_WARNING = "parent_grouped"

ResolvedCandidate = tuple[FusedCandidate, EvidenceReference, str]


@dataclass(frozen=True)
class _ParentGroup:
    """The best-ranked window of one parent unit and how many ranked windows it stands for."""

    item: ResolvedCandidate
    chunk: ChunkSnapshot
    window_count: int = 1


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
        resolved: list[ResolvedCandidate] = []
        chunks: dict[tuple[str, str], ChunkSnapshot] = {}
        retired_by_document: dict[str, bool] = {}
        for candidate in candidates:
            if self._is_retired(candidate.document_id, retired_by_document):
                continue
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
            chunks[(candidate.vault_id, candidate.chunk_id)] = chunk

        ranked = rank_resolved_candidates(resolved, mode=mode)
        groups = _group_by_parent(ranked, chunks)
        results = tuple(self._result_for_group(group=group, rank=rank) for rank, group in enumerate(groups, start=1))
        return results, dropped, tuple(warnings)

    def _is_retired(self, document_id: str, cache: dict[str, bool]) -> bool:
        # 결정S14: status `retired` pages are left out of default search (INV-05 exception, docs/DECISIONS.md).
        # `deprecated` pages stay. A missing document falls through to the missing-evidence path.
        if document_id not in cache:
            document = self._metadata_store.resolve_document(document_id)
            cache[document_id] = document is not None and document.frontmatter.get("status") == RETIRED_STATUS
        return cache[document_id]

    def _result_for_group(self, *, group: _ParentGroup, rank: int) -> RetrievalResult:
        candidate, evidence, summary = group.item
        if group.chunk.parent_key is None:
            return self._result_for_candidate(candidate=candidate, evidence=evidence, summary=summary, rank=rank)
        # Spec 2026-11-05 §4.2.6-6: a session result points at the whole exchange and quotes its best window.
        if group.chunk.parent_locators:
            evidence = replace(evidence, source_locators=group.chunk.parent_locators)
        warnings: tuple[RetrievalWarning, ...] = ()
        if group.window_count > 1:
            warnings = (
                RetrievalWarning(
                    code=PARENT_GROUPED_WARNING,
                    message=(
                        f"{group.window_count} windows of {group.chunk.parent_key} matched; "
                        f"shown once as the best-ranked window {candidate.chunk_id}."
                    ),
                    severity="info",
                ),
            )
        result = self._result_for_candidate(candidate=candidate, evidence=evidence, summary=summary, rank=rank)
        return replace(result, warnings=warnings)

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


def _group_by_parent(
    ranked: list[ResolvedCandidate], chunks: dict[tuple[str, str], ChunkSnapshot]
) -> tuple[_ParentGroup, ...]:
    """Keep ranked order. Windows sharing a `parent_key` fold into the first (best-ranked) one."""
    groups: list[_ParentGroup] = []
    position_by_parent: dict[tuple[str, str], int] = {}
    for item in ranked:
        chunk = chunks[(item[0].vault_id, item[0].chunk_id)]
        if chunk.parent_key is None:
            groups.append(_ParentGroup(item=item, chunk=chunk))
            continue
        parent = (item[0].vault_id, chunk.parent_key)
        position = position_by_parent.get(parent)
        if position is None:
            position_by_parent[parent] = len(groups)
            groups.append(_ParentGroup(item=item, chunk=chunk))
        else:
            groups[position] = replace(groups[position], window_count=groups[position].window_count + 1)
    return tuple(groups)


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
