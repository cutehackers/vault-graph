from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

from vault_graph.indexing.ingestion.document_authority import DocumentRole, provenance_paths
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker
from vault_graph.retrieval.search.candidate_ranking import (
    FusedCandidate,
    document_names,
    document_score,
    role_weight,
    sort_resolved_candidates,
    title_match_rank,
    title_signal_score,
)
from vault_graph.retrieval.search.retrieval_result import (
    ResultLifecycle,
    RetrievalResult,
    RetrievalWarning,
    StoreRevision,
)
from vault_graph.retrieval.search.search_response import SearchMode, SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

RETIRED_STATUS = "retired"
PARENT_GROUPED_WARNING = "parent_grouped"
DUPLICATE_CONTENT_WARNING = "duplicate_content"

ResolvedCandidate = tuple[FusedCandidate, EvidenceReference, str]


@dataclass(frozen=True)
class _ParentGroup:
    """One result unit: the best-ranked chunk of a document (or of a session exchange) and its score.

    ``window_count`` is how many ranked chunks the unit stands for. ``duplicates`` names the same content
    in other Vaults (`<vault_id>:<path>`), folded into this unit (spec 2026-11-05 §10.2 원인4).
    """

    item: ResolvedCandidate
    chunk: ChunkSnapshot
    window_count: int = 1
    score: float = 0.0
    document: DocumentSnapshot | None = None
    duplicates: tuple[str, ...] = ()


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
        include_retired: bool = False,
        vault_order: tuple[str, ...] = (),
        query_text: str = "",
    ) -> tuple[tuple[RetrievalResult, ...], int, tuple[SearchWarning, ...]]:
        """Resolve fused chunk candidates into ranked results, one per document or session exchange.

        Spec 2026-11-05 §10.2: chunks group per unit and the unit score is ``document_score`` times the
        mode's role weight (원인1·3). A unit whose page title or alias the query names gets the title
        signal added once (원인5, ``title_signal_score``). Knowledge mode folds pages joined by
        `supersedes`/`superseded_by` (원인2). The same content in several Vaults returns once, from the
        earliest Vault of ``vault_order`` (원인4).
        """
        dropped = 0
        warnings: list[SearchWarning] = []
        resolved: list[ResolvedCandidate] = []
        chunks: dict[tuple[str, str], ChunkSnapshot] = {}
        documents: dict[str, DocumentSnapshot | None] = {}
        for candidate in candidates:
            document = self._document(candidate.document_id, documents)
            if not include_retired and _is_retired(document):
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

        ranked = sort_resolved_candidates(resolved)
        groups = _group_by_unit(ranked, chunks, documents=documents, mode=mode, query_text=query_text)
        if mode == "knowledge":
            groups = _fold_replacements(groups)
        groups = _fold_duplicate_content(groups, vault_order=vault_order)
        families: dict[tuple[str, str], tuple[EvidenceReference, ...]] = {}
        results = tuple(
            self._result_for_group(group=group, rank=rank, families=families)
            for rank, group in enumerate(groups, start=1)
        )
        if include_retired:
            # Spec 2026-11-05 §4.4.13-1: with `include_retired`, every result carries its page lifecycle.
            results = tuple(
                replace(result, lifecycle=_lifecycle(self._document(result.evidence[0].document_id, documents)))
                for result in results
            )
        return results, dropped, tuple(warnings)

    def _document(self, document_id: str, cache: dict[str, DocumentSnapshot | None]) -> DocumentSnapshot | None:
        if document_id not in cache:
            cache[document_id] = self._metadata_store.resolve_document(document_id)
        return cache[document_id]

    def _result_for_group(
        self, *, group: _ParentGroup, rank: int, families: dict[tuple[str, str], tuple[EvidenceReference, ...]]
    ) -> RetrievalResult:
        candidate, evidence, summary = group.item
        warnings: list[RetrievalWarning] = []
        if group.chunk.parent_key is not None:
            # Spec 2026-11-05 §4.2.6-6: a session result points at the whole exchange and quotes its best window.
            if group.chunk.parent_locators:
                evidence = replace(evidence, source_locators=group.chunk.parent_locators)
            if group.window_count > 1:
                warnings.append(
                    RetrievalWarning(
                        code=PARENT_GROUPED_WARNING,
                        message=(
                            f"{group.window_count} windows of {group.chunk.parent_key} matched; "
                            f"shown once as the best-ranked window {candidate.chunk_id}."
                        ),
                        severity="info",
                    )
                )
        elif group.window_count > 1:
            # Spec 2026-11-05 §10.2 원인3: a document result quotes its best chunk.
            warnings.append(
                RetrievalWarning(
                    code=PARENT_GROUPED_WARNING,
                    message=(
                        f"{group.window_count} chunks of {evidence.path} matched; "
                        f"shown once as the best-ranked chunk {candidate.chunk_id}."
                    ),
                    severity="info",
                )
            )
        if group.duplicates:
            warnings.append(
                RetrievalWarning(
                    code=DUPLICATE_CONTENT_WARNING,
                    message=(
                        f"The same content is also in {', '.join(group.duplicates)}; "
                        f"shown once from Vault {candidate.vault_id}."
                    ),
                    severity="info",
                )
            )
        result = self._result_for_candidate(
            candidate=candidate, evidence=evidence, summary=summary, rank=rank, families=families
        )
        return replace(result, warnings=tuple(warnings))

    def _result_for_candidate(
        self,
        *,
        candidate: FusedCandidate,
        evidence: EvidenceReference,
        summary: str,
        rank: int,
        families: dict[tuple[str, str], tuple[EvidenceReference, ...]],
    ) -> RetrievalResult:
        family_id = evidence.provenance_family_id or evidence.document_id
        family = families.get((evidence.vault_id, family_id))
        if family is None:
            # Only the first reference of each document is kept below, so a store that returns just those is enough.
            # One search reads each family once (spec 2026-11-11 §4.2.6).
            family_reader = getattr(self._metadata_store, "list_family_document_evidence", None) or getattr(
                self._metadata_store, "list_family_evidence", None
            )
            family = (
                family_reader(vault_id=evidence.vault_id, provenance_family_id=family_id)
                if callable(family_reader)
                else ()
            )
            families[(evidence.vault_id, family_id)] = family
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


def _is_retired(document: DocumentSnapshot | None) -> bool:
    # 결정S14: status `retired` pages are left out of default search (INV-05 exception, docs/DECISIONS.md).
    # `deprecated` pages stay. A missing document falls through to the missing-evidence path.
    return document is not None and document.frontmatter.get("status") == RETIRED_STATUS


def _lifecycle(document: DocumentSnapshot | None) -> ResultLifecycle:
    frontmatter = document.frontmatter if document is not None else {}
    superseded_by = frontmatter.get("superseded_by")
    targets = superseded_by if isinstance(superseded_by, list | tuple) else [superseded_by]
    return ResultLifecycle(
        status=_frontmatter_text(frontmatter.get("status")),
        retired_reason=_frontmatter_text(frontmatter.get("retired_reason")),
        retired_at=_frontmatter_text(frontmatter.get("retired_at")),
        superseded_by=tuple(text for text in (_frontmatter_text(target) for target in targets) if text is not None),
    )


def _frontmatter_text(value: object) -> str | None:
    if value is None:
        return None
    text = value.isoformat() if isinstance(value, date) else str(value).strip()
    return text or None


def _group_by_unit(
    ranked: list[ResolvedCandidate],
    chunks: dict[tuple[str, str], ChunkSnapshot],
    *,
    documents: dict[str, DocumentSnapshot | None],
    mode: SearchMode,
    query_text: str = "",
) -> tuple[_ParentGroup, ...]:
    """Fold ranked chunks into one unit per session exchange (`parent_key`) or per document, best chunk first.

    Units are ordered by ``document_score`` of their chunks' fused scores plus the title signal, times the
    role weight, then by the best chunk's ranking key, so equal scores keep the chunk order. The title
    signal depends on the document only, so a page that matches in its page card and in several windows
    gets it once.
    """
    members: dict[tuple[str, str, str], list[ResolvedCandidate]] = {}
    for item in ranked:
        candidate = item[0]
        chunk = chunks[(candidate.vault_id, candidate.chunk_id)]
        key = (
            (candidate.vault_id, "exchange", chunk.parent_key)
            if chunk.parent_key is not None
            else (candidate.vault_id, "document", candidate.document_id)
        )
        members.setdefault(key, []).append(item)
    groups: list[tuple[int, _ParentGroup]] = []
    for position, items in enumerate(members.values()):
        best = items[0]
        document = documents.get(best[0].document_id)
        score = document_score(tuple(item[0].fused_score for item in items))
        score += title_signal_score(title_match_rank(query_text, document_names(document)))
        groups.append(
            (
                position,
                _ParentGroup(
                    item=best,
                    chunk=chunks[(best[0].vault_id, best[0].chunk_id)],
                    window_count=len(items),
                    score=score * role_weight(mode, best[1].source_role),
                    document=document,
                ),
            )
        )
    groups.sort(key=lambda entry: (-entry[1].score, entry[0]))
    return tuple(group for _, group in groups)


def _fold_replacements(groups: tuple[_ParentGroup, ...]) -> tuple[_ParentGroup, ...]:
    """Keep the highest-ranked page of each `supersedes`/`superseded_by` chain (spec 2026-11-05 §10.2 원인2).

    Pages that only share a `derived_from` or `canonical_source` target stay separate results.
    """
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(key: tuple[str, str]) -> tuple[str, str]:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for group in groups:
        evidence = group.item[1]
        own = find((evidence.vault_id, evidence.path))
        for target in _replacement_paths(group.document):
            other = find((evidence.vault_id, target))
            if other != own:
                parent[max(own, other)] = min(own, other)
                own = min(own, other)
    kept: list[_ParentGroup] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        evidence = group.item[1]
        if group.chunk.parent_key is not None:
            kept.append(group)
            continue
        root = find((evidence.vault_id, evidence.path))
        if root in seen:
            continue
        seen.add(root)
        kept.append(group)
    return tuple(kept)


def _replacement_paths(document: DocumentSnapshot | None) -> tuple[str, ...]:
    if document is None:
        return ()
    targets: list[str] = []
    for field_name in ("supersedes", "superseded_by"):
        value = document.frontmatter.get(field_name)
        if isinstance(value, str):
            targets.append(value)
        elif isinstance(value, list | tuple):
            targets.extend(item for item in value if isinstance(item, str))
    # `provenance_paths` normalizes wiki links and Vault-relative paths the same way the index does.
    return provenance_paths({"supersedes": targets})


def _fold_duplicate_content(
    groups: tuple[_ParentGroup, ...], *, vault_order: tuple[str, ...]
) -> tuple[_ParentGroup, ...]:
    """Fold units with the same document `content_hash` from different Vaults into one result.

    The folded result takes the position of the highest-ranked copy and shows the copy from the Vault
    that comes first in ``vault_order`` (the requested scope order). The others are listed in it.
    """
    order = {vault_id: index for index, vault_id in enumerate(vault_order)}
    clusters: list[list[_ParentGroup]] = []
    cluster_by_key: dict[tuple[str, str | None], int] = {}
    for group in groups:
        key = None if group.document is None else (group.document.content_hash, group.chunk.parent_key)
        position = cluster_by_key.get(key) if key is not None else None
        if position is not None and all(
            member.item[0].vault_id != group.item[0].vault_id for member in clusters[position]
        ):
            clusters[position].append(group)
            continue
        if key is not None and position is None:
            cluster_by_key[key] = len(clusters)
        clusters.append([group])
    folded: list[_ParentGroup] = []
    for cluster in clusters:
        if len(cluster) == 1:
            folded.append(cluster[0])
            continue
        shown = min(
            cluster, key=lambda member: (order.get(member.item[0].vault_id, len(order)), member.item[0].vault_id)
        )
        others = tuple(f"{member.item[0].vault_id}:{member.item[1].path}" for member in cluster if member is not shown)
        folded.append(replace(shown, duplicates=others))
    return tuple(folded)


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
