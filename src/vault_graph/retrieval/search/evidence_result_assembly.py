from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from vault_graph.indexing.ingestion.document_authority import DocumentRole, provenance_paths
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.indexing.ingestion.session_group import session_group_key
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker
from vault_graph.retrieval.search.candidate_ranking import (
    FusedCandidate,
    document_names,
    document_score,
    fact_key_score,
    is_fact_key,
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
REPLACED_PAGES_WARNING = "replaced_pages_attached"
SESSION_EXCHANGES_WARNING = "session_exchanges_attached"
FACT_SOURCE_MISSING_WARNING = "fact_source_missing"
FACT_ATTACHMENT_SUFFIX = ".facts.md"
# Other exchanges of one session attached to its result as evidence references (spec 2026-11-16 D5).
SESSION_EXCHANGE_LIMIT = 3

ResolvedCandidate = tuple[FusedCandidate, EvidenceReference, str]
# What makes two session exchanges the same content: the exchange keyword metadata and the `content_hash` of
# every window of the exchange, in document order.
ExchangeSignature = tuple[str | None, tuple[str, ...]]


@dataclass(frozen=True)
class _ParentGroup:
    """One result unit: the best-ranked chunk of a document (or of a session exchange) and its score.

    ``window_count`` is how many ranked chunks the unit stands for. ``duplicates`` names the same content
    in other Vaults (`<vault_id>:<path>`), folded into this unit (spec 2026-11-05 §10.2 원인4).
    ``copies`` are the lower-ranked units of the same Vault that hold the same session exchange, and
    ``replaced`` are the lower-ranked pages of this page's `supersedes`/`superseded_by` chain. Both stay
    reachable as extra evidence of this unit's result (spec 2026-11-11 결정17).
    ``session_exchanges`` are the lower-ranked exchange units of the same session in the same Vault, in
    rank order (spec 2026-11-16 D2). All are kept so the result can count them. At most
    ``SESSION_EXCHANGE_LIMIT`` are attached.
    """

    item: ResolvedCandidate
    chunk: ChunkSnapshot
    window_count: int = 1
    score: float = 0.0
    document: DocumentSnapshot | None = None
    duplicates: tuple[str, ...] = ()
    copies: tuple[_ParentGroup, ...] = ()
    replaced: tuple[_ParentGroup, ...] = ()
    session_exchanges: tuple[_ParentGroup, ...] = ()


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
        include_fact_keys: bool = True,
    ) -> tuple[tuple[RetrievalResult, ...], tuple[str, ...], int, tuple[SearchWarning, ...]]:
        """Resolve fused chunk candidates into ranked results, one per document or session exchange.

        Returns the results, the reranking text of each result in the same order (`_rerank_passage`), the
        number of dropped candidates and the warnings. The reranking text stays inside search.

        Spec 2026-11-05 §10.2: chunks group per unit and the unit score is ``document_score`` times the
        mode's role weight (원인1·3). A unit whose page title or alias the query names gets the title
        signal added once (원인5, ``title_signal_score``). Knowledge mode folds pages joined by
        `supersedes`/`superseded_by` (원인2). The same content in several Vaults returns once, from the
        earliest Vault of ``vault_order`` (원인4).

        Spec 2026-11-11 결정17: the same session exchange in several files of one Vault returns once, at the
        highest-ranked copy. Folded copies and replaced pages are listed after the result's own evidence.

        Spec 2026-11-16 D2: the exchanges of one session in one Vault return once, at the highest-ranked
        exchange. Up to three other exchanges are listed after its own evidence and copies.

        Spec 2026-11-16 D21, I3, F12: a session fact chunk is a key for its original exchange. Its fused score
        is multiplied by ``FACT_KEY_WEIGHT`` and it groups with the exchange's windows by ``parent_key``. A unit
        matched only by facts shows the exchange's first window instead (`_fact_source_window`). When that
        window is not in the index the unit is dropped with a ``fact_source_missing`` warning. Fact text is
        never a summary, title or evidence. With ``include_fact_keys`` False fact chunks are skipped.
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
            if is_fact_key(chunk):
                if not include_fact_keys:
                    continue
                candidate = replace(candidate, fused_score=fact_key_score(candidate.fused_score))
            resolved.append((candidate, evidence, _excerpt(chunk.text)))
            chunks[(candidate.vault_id, candidate.chunk_id)] = chunk

        ranked = sort_resolved_candidates(resolved)
        missing_sources: list[ResolvedCandidate] = []

        def source_window(fact: ResolvedCandidate) -> tuple[ResolvedCandidate, ChunkSnapshot] | None:
            found = self._fact_source_window(fact, chunks[(fact[0].vault_id, fact[0].chunk_id)], documents)
            if found is None or found[0][1].source_role not in allowed_roles:
                missing_sources.append(fact)
                return None
            return found

        groups = _group_by_unit(
            ranked, chunks, documents=documents, mode=mode, query_text=query_text, source_window=source_window
        )
        for fact in missing_sources:
            dropped += 1
            warnings.append(_fact_source_missing(fact, chunks[(fact[0].vault_id, fact[0].chunk_id)]))
        if mode == "knowledge":
            groups = _fold_replacements(groups)
        groups = _fold_exchange_copies(groups, signature=self._exchange_signature)
        groups = _fold_session_exchanges(groups)
        groups = _fold_duplicate_content(groups, vault_order=vault_order)
        families: dict[tuple[str, str], tuple[EvidenceReference, ...]] = {}
        results = tuple(
            self._result_for_group(group=group, rank=rank, families=families)
            for rank, group in enumerate(groups, start=1)
        )
        passages = tuple(_rerank_passage(group) for group in groups)
        if include_retired:
            # Spec 2026-11-05 §4.4.13-1: with `include_retired`, every result carries its page lifecycle.
            results = tuple(
                replace(result, lifecycle=_lifecycle(self._document(result.evidence[0].document_id, documents)))
                for result in results
            )
        return results, passages, dropped, tuple(warnings)

    def _document(self, document_id: str, cache: dict[str, DocumentSnapshot | None]) -> DocumentSnapshot | None:
        if document_id not in cache:
            cache[document_id] = self._metadata_store.resolve_document(document_id)
        return cache[document_id]

    def _fact_source_window(
        self,
        fact: ResolvedCandidate,
        fact_chunk: ChunkSnapshot,
        documents: dict[str, DocumentSnapshot | None],
    ) -> tuple[ResolvedCandidate, ChunkSnapshot] | None:
        """The first window of a fact's original exchange, standing in for the fact, or None when not indexed.

        The exchange is in the part file the attachment names (`<part name>.facts.md` next to `<part name>.md`).
        Only that file is read, and only for a unit that no window of the exchange matched (spec 2026-11-16
        D21). The window takes the fact's fused score and signals, so the unit ranks where the fact did.
        """
        candidate = fact[0]
        path = _fact_source_path(fact_chunk.path)
        if path is None or fact_chunk.parent_key is None:
            return None
        state = self._metadata_store.document_state(candidate.vault_id, path)
        if state.document_id is None or state.is_tombstoned:
            return None
        windows = sorted(
            (
                chunk
                for chunk in self._metadata_store.list_document_chunks(
                    vault_id=candidate.vault_id, document_id=state.document_id
                )
                if chunk.parent_key == fact_chunk.parent_key and not is_fact_key(chunk)
            ),
            key=lambda chunk: chunk.document_order,
        )
        if not windows:
            return None
        window = windows[0]
        evidence = self._evidence_linker.resolve_evidence(((candidate.vault_id, window.document_id, window.chunk_id),))[
            0
        ].evidence
        if evidence is None:
            return None
        self._document(window.document_id, documents)
        stand_in = replace(candidate, document_id=window.document_id, chunk_id=window.chunk_id)
        return (stand_in, evidence, _excerpt(window.text)), window

    def _exchange_signature(self, group: _ParentGroup) -> ExchangeSignature | None:
        """Content identity of the whole exchange a session unit stands for, or None when it cannot be read.

        Window text is the exchange's turns without file positions, so the same exchange written into two
        session files gives the same window hashes. One narrow read per asked unit (spec 2026-11-11 §4.2.6).
        """
        candidate = group.item[0]
        parent_key = group.chunk.parent_key
        if parent_key is None:
            return None
        reader = getattr(self._metadata_store, "list_parent_chunk_hashes", None)
        if callable(reader):
            hashes = tuple(
                reader(vault_id=candidate.vault_id, document_id=candidate.document_id, parent_key=parent_key)
            )
        else:
            hashes = tuple(
                chunk.content_hash
                for chunk in self._metadata_store.list_document_chunks(
                    vault_id=candidate.vault_id, document_id=candidate.document_id
                )
                if chunk.parent_key == parent_key
            )
        return (group.chunk.keyword_metadata, hashes) if hashes else None

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
        if group.copies:
            names = ", ".join(f"{copy.item[0].vault_id}:{copy.item[1].path}" for copy in group.copies)
            warnings.append(
                RetrievalWarning(
                    code=DUPLICATE_CONTENT_WARNING,
                    message=f"The same exchange is also in {names}; shown once from {evidence.path}.",
                    severity="info",
                )
            )
        if group.replaced:
            names = ", ".join(page.item[1].path for page in group.replaced)
            warnings.append(
                RetrievalWarning(
                    code=REPLACED_PAGES_WARNING,
                    message=(
                        f"Pages joined to {evidence.path} by supersedes/superseded_by are attached as "
                        f"evidence: {names}."
                    ),
                    severity="info",
                )
            )
        attached_exchanges = group.session_exchanges[:SESSION_EXCHANGE_LIMIT]
        if group.session_exchanges:
            total = len(group.session_exchanges) + 1
            left_out = len(group.session_exchanges) - len(attached_exchanges)
            session = session_group_key(group.document.frontmatter) if group.document is not None else None
            warnings.append(
                RetrievalWarning(
                    code=SESSION_EXCHANGES_WARNING,
                    message=(
                        f"{total} exchanges of session {session} matched; shown once as the best-ranked exchange "
                        f"{group.chunk.parent_key}, {len(attached_exchanges)} other exchanges attached as evidence"
                        + (f", {left_out} left out." if left_out else ".")
                    ),
                    severity="info",
                )
            )
        result = self._result_for_candidate(
            candidate=candidate, evidence=evidence, summary=summary, rank=rank, families=families
        )
        # The result's own evidence stays first. Copies, replaced pages and the session's other exchanges
        # (each with its own copies) follow in rank order. They are references only: the summary stays the
        # best window of this unit (spec 2026-11-16 D5).
        attached = (
            *(_unit_evidence(copy) for copy in group.copies),
            *(page.item[1] for page in group.replaced),
            *(
                item
                for exchange in attached_exchanges
                for item in (_unit_evidence(exchange), *(_unit_evidence(copy) for copy in exchange.copies))
            ),
        )
        return replace(result, evidence=_unique_evidence((evidence, *attached)), warnings=tuple(warnings))

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


def _rerank_passage(group: _ParentGroup) -> str:
    """Text the reranking model reads for a unit, from text this search already read (spec 2026-11-13 D7, I6).

    A session exchange gives its quoted window. A document gives its frontmatter title and summary, when
    present, then the full text of its best chunk. A best chunk that is the page card already holds those
    values, so it is used alone.
    """
    if group.chunk.parent_key is not None or group.chunk.chunk_kind == "page_card" or group.document is None:
        return group.chunk.text
    frontmatter = group.document.frontmatter
    parts = (_frontmatter_text(frontmatter.get("title")), _frontmatter_text(frontmatter.get("summary")))
    return "\n".join((*(part for part in parts if part is not None), group.chunk.text))


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
    source_window: Callable[[ResolvedCandidate], tuple[ResolvedCandidate, ChunkSnapshot] | None] | None = None,
) -> tuple[_ParentGroup, ...]:
    """Fold ranked chunks into one unit per session exchange (`parent_key`) or per document, best chunk first.

    Session fact chunks share the `parent_key` of their exchange, so they fold into its unit, add to its
    score and never become its shown chunk. A unit of facts only shows ``source_window`` of its best fact
    instead, and is left out when that gives None (spec 2026-11-16 D21, F12). ``window_count`` counts windows.

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
        shown = [item for item in items if not is_fact_key(chunks[(item[0].vault_id, item[0].chunk_id)])]
        if shown:
            best = shown[0]
            best_chunk = chunks[(best[0].vault_id, best[0].chunk_id)]
        else:
            found = source_window(items[0]) if source_window is not None else None
            if found is None:
                continue
            best, best_chunk = found
        document = documents.get(best[0].document_id)
        score = document_score(tuple(item[0].fused_score for item in items))
        score += title_signal_score(title_match_rank(query_text, document_names(document)))
        groups.append(
            (
                position,
                _ParentGroup(
                    item=best,
                    chunk=best_chunk,
                    window_count=max(len(shown), 1),
                    score=score * role_weight(mode, best[1].source_role),
                    document=document,
                ),
            )
        )
    groups.sort(key=lambda entry: (-entry[1].score, entry[0]))
    return tuple(group for _, group in groups)


def _fold_replacements(groups: tuple[_ParentGroup, ...]) -> tuple[_ParentGroup, ...]:
    """Keep the highest-ranked page of each `supersedes`/`superseded_by` chain (spec 2026-11-05 §10.2 원인2).

    The lower-ranked pages of the chain move into the kept unit's ``replaced``, in rank order, so the result
    still names them (spec 2026-11-11 결정17). Pages that only share a `derived_from` or `canonical_source`
    target stay separate results.
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
    position_by_root: dict[tuple[str, str], int] = {}
    for group in groups:
        evidence = group.item[1]
        if group.chunk.parent_key is not None:
            kept.append(group)
            continue
        root = find((evidence.vault_id, evidence.path))
        position = position_by_root.get(root)
        if position is not None:
            kept[position] = replace(kept[position], replaced=(*kept[position].replaced, group))
            continue
        position_by_root[root] = len(kept)
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


def _fold_exchange_copies(
    groups: tuple[_ParentGroup, ...], *, signature: Callable[[_ParentGroup], ExchangeSignature | None]
) -> tuple[_ParentGroup, ...]:
    """Fold session exchanges with the same content inside one Vault into the highest-ranked copy.

    Session files that continue one conversation hold the same exchange again. ``signature`` gives the
    identity of a whole exchange. It is asked only for units that share the Vault and the exchange question
    (the chunk `section`) with another unit, so a search with no copy candidates reads nothing extra. The
    lower-ranked copies move into the kept unit's ``copies``, in rank order.

    A forked session, or a file captured before the exchange ended, holds only the first part of the
    exchange. Such a unit is a copy too (`_same_exchange`).
    """
    question_counts: dict[tuple[str, str | None], int] = {}
    for group in groups:
        if group.chunk.parent_key is not None:
            key = (group.item[0].vault_id, group.chunk.section)
            question_counts[key] = question_counts.get(key, 0) + 1
    kept: list[_ParentGroup] = []
    kept_contents: dict[tuple[str, str | None], list[tuple[ExchangeSignature, int]]] = {}
    for group in groups:
        vault_id = group.item[0].vault_id
        if group.chunk.parent_key is None or question_counts[(vault_id, group.chunk.section)] < 2:
            kept.append(group)
            continue
        content = signature(group)
        seen = kept_contents.setdefault((vault_id, group.chunk.section), [])
        position = (
            next((index for other, index in seen if _same_exchange(content, other)), None)
            if content is not None
            else None
        )
        if position is not None:
            kept[position] = replace(kept[position], copies=(*kept[position].copies, group))
            continue
        if content is not None:
            seen.append((content, len(kept)))
        kept.append(group)
    return tuple(kept)


def _fold_session_exchanges(groups: tuple[_ParentGroup, ...]) -> tuple[_ParentGroup, ...]:
    """Fold the exchange units of one session inside one Vault into the highest-ranked one (spec 2026-11-16 D2).

    The session key is `<agent>:<session_id>` of the unit's document (D3), so the part files of one session
    fold together. The kept unit keeps its score and place (D4). The lower-ranked exchanges move into its
    ``session_exchanges``, in rank order. Units of other Vaults, pages, and session files without `agent`
    or `session_id` stay separate results (F1, F2).
    """
    kept: list[_ParentGroup] = []
    position_by_session: dict[tuple[str, str], int] = {}
    for group in groups:
        session = (
            session_group_key(group.document.frontmatter)
            if group.chunk.parent_key is not None and group.document is not None
            else None
        )
        if session is None:
            kept.append(group)
            continue
        key = (group.item[0].vault_id, session)
        position = position_by_session.get(key)
        if position is not None:
            kept[position] = replace(kept[position], session_exchanges=(*kept[position].session_exchanges, group))
            continue
        position_by_session[key] = len(kept)
        kept.append(group)
    return tuple(kept)


def _same_exchange(first: ExchangeSignature, second: ExchangeSignature) -> bool:
    """True for the same exchange, or for one exchange and a shorter copy of its first part.

    The signatures are equal, or the shorter one's windows, all but its last, open the longer one. The last
    window of the shorter copy is left out because it ends where that file stopped, so its text differs
    from the same window in the longer copy. A one-window exchange has to be equal.
    """
    if first == second:
        return True
    shorter, longer = sorted((first[1], second[1]), key=len)
    shared = len(shorter) - 1
    return shared >= 1 and len(longer) > len(shorter) and longer[:shared] == shorter[:shared]


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


def _fact_source_path(path: str) -> str | None:
    """`<part name>.md` for a `<part name>.facts.md` attachment path (contract vault-session-facts-v1 §3)."""
    if not path.endswith(FACT_ATTACHMENT_SUFFIX):
        return None
    return f"{path.removesuffix(FACT_ATTACHMENT_SUFFIX)}.md"


def _fact_source_missing(fact: ResolvedCandidate, chunk: ChunkSnapshot) -> SearchWarning:
    """Spec 2026-11-16 F12. Names the fact chunk and its exchange, never the fact text."""
    candidate = fact[0]
    return SearchWarning(
        code=FACT_SOURCE_MISSING_WARNING,
        message=(
            f"Fact key {candidate.chunk_id} in {chunk.path} points at exchange {chunk.parent_key}, which is not in "
            "the index; the fact key was dropped."
        ),
        severity="warning",
        affected_vault_ids=(candidate.vault_id,),
        document_id=candidate.document_id,
        chunk_id=candidate.chunk_id,
    )


def _unit_evidence(group: _ParentGroup) -> EvidenceReference:
    """Evidence of a unit as a result shows it: a session unit points at its whole exchange."""
    evidence = group.item[1]
    if group.chunk.parent_key is not None and group.chunk.parent_locators:
        return replace(evidence, source_locators=group.chunk.parent_locators)
    return evidence


def _unique_evidence(evidence: tuple[EvidenceReference, ...]) -> tuple[EvidenceReference, ...]:
    by_chunk: dict[tuple[str, str, str], EvidenceReference] = {}
    for item in evidence:
        by_chunk.setdefault((item.vault_id, item.document_id, item.chunk_id), item)
    return tuple(by_chunk.values())


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
