"""Cleanup candidates: L1 notes, session exchanges, merge pairs, retire pages and the project brief
(spec 2026-11-05 §4.4.4, §4.4.7).

Acceptance A-22, A-38, A-39, A-25, A-35.

The cleanup bundle is deterministic: the same index, the same L1 notes, the same Vault pages and
the same review records give the same result. No LLM runs here. The calling agent decides what
to remember. Callers (composition) read the inputs and pass them in:

- L1 notes as ``L1Note`` and the ``raw_sha256`` values of the Vault's ``raw/imports/claude-memory/``
  copies. A note whose sha256 is among them is already kept. ``MEMORY.md`` is the L1 index, not a note.
- Indexed session exchanges as ``SessionExchange`` (one per ``parent_key`` of the v1/v2 session chunkers).
- Vault pages as ``WikiPageText``. Only ``wiki/`` pages count as citing an exchange.
- Candidate keys already recorded in the Graph Home ``memory/reviewed.jsonl``.
- A ``SimilarPageFinder`` for comparison material. The real finder searches with ``include_retired``
  (§4.4.13-2), so retired pages come back too and ``ComparisonPage.label`` marks them "폐기됨: <이유>".
- Indexed ``wiki/`` pages as ``MemoryPage`` for the merge and retire rules, their embedding vectors,
  the code references composition found gone from the registered repositories (M11 lives outside
  M10, §4.4.12), and the Graph Home usage events.
- The project brief rule result (``brief.project_brief_staleness``, §4.4.7).

Merge (§4.4.4): two current pages in the project scope whose embedding cosine similarity is at least
``merge_threshold``. The §4.4.10 evaluation (task #40) sets the value. Until then
``DEFAULT_MERGE_SIMILARITY`` keeps only near duplicates.

Retire (§4.4.4, risk D10): a current, not pinned page in the project scope whose cited code is gone
(``code_gone``), or that recall injected in the last 90 days and nobody opened (``unused``). The
``unused`` signal needs a usage log that reaches back over the whole window: a log younger than 90
days, for example after the Graph Home was deleted, gives no ``unused`` candidate. Nothing here
changes a page. The calling agent decides, and only Vault tools write (A-25).

Brief (§4.4.7, rule 4): one candidate when the brief rule says the brief needs an update. Its key is
``brief:<project>:<12 hex>`` of the counted decision pages, ``location`` is the brief path (the page
may not exist yet), ``targets`` is the brief when it exists, and the comparison material is the new
decision pages, not a similarity search. vg never writes the brief (A-27).

Exchange citation (rule 2, risk D2 and D11). The Vault cites a session file as a ``raw/sessions/...``
path with an optional ``#sha256=<hash>`` (vault-builder OPERATING-SCHEMA §16.1 "Claim evidence").
Vault lint reads that path up to whitespace, so vg writes an exchange location after a space:
``<path> L<first>-L<last>``. On the same line after a session path, a line range (``L12-L40``,
``#L12-L40``, ``lines 12-40``) cites every exchange of that file it overlaps, and the exchange id or
its first 8 characters cites that exchange. A path with neither cites no exchange.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol

from vault_graph.context.memory.brief import ProjectBriefStaleness
from vault_graph.context.memory.project_memory import STALE_STATUSES
from vault_graph.context.memory.project_scope import VaultProjectScope, page_in_project

if TYPE_CHECKING:
    from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

SESSION_CANDIDATE_MAX_AGE = timedelta(days=180)
COMPARISON_PAGE_LIMIT = 5
COMPARISON_FETCH_LIMIT = 20
L1_INDEX_NAME = "MEMORY.md"
L1_KEY_PREFIX = "l1:"
SESSION_KEY_PREFIX = "session:"
MERGE_KEY_PREFIX = "merge:"
RETIRE_KEY_PREFIX = "retire:"
TOOL_ERROR_UNRESOLVED = "tool_error_unresolved"
# Spec §4.4.4: "임계값은 4.4.10 평가로 정함". Task #40 measures it. Until then cosine 0.92 keeps only
# near-duplicate pages. Callers pass ``merge_threshold`` to try another value.
DEFAULT_MERGE_SIMILARITY = 0.92
RETIRE_UNUSED_WINDOW = timedelta(days=90)
# Pages that are not current memory: recall leaves them out (``STALE_STATUSES``).
NOT_CURRENT_STATUSES = frozenset(STALE_STATUSES)
# Statuses shown as "폐기됨" in comparison material: what ``retire_memory`` writes, and replaced pages.
RETIRED_LABEL_STATUSES = frozenset({"retired", "deprecated", "superseded"})
# Generated navigation and source pages are not memories to merge or retire.
NON_MEMORY_PAGE_TYPES = frozenset({"index", "log", "map", "overview", "source"})

# Signal words for ordering session exchanges. Matched case-folded as substrings of the human text.
# Keep them few and fixed: they only order candidates, they never decide what is remembered.
CORRECTION_SIGNALS: tuple[str, ...] = (
    "아니야",
    "아니라",
    "그게 아니",
    "틀렸",
    "잘못",
    "하지 마",
    "하지마",
    "wrong",
    "that's not",
    "not what i",
)
DECISION_WORDS: tuple[str, ...] = (
    "결정",
    "하기로",
    "정했",
    "채택",
    "decide",
    "decision",
    "go with",
)
DIRECTION_CHANGE_WORDS: tuple[str, ...] = (
    "대신",
    "말고",
    "다른 방법",
    "다른 방식",
    "instead",
    "switch to",
    "different approach",
)

CandidateKind = Literal["l1_note", "session_exchange", "merge", "retire", "brief"]
CANDIDATE_KINDS: tuple[CandidateKind, ...] = ("l1_note", "session_exchange", "merge", "retire", "brief")
SessionSignal = Literal["correction", "decision", "unresolved_error_direction_change", "none"]
RetireSignal = Literal["code_gone", "unused"]
PageKey = tuple[str, str]

_SESSION_PATH_RE = re.compile(r"raw/sessions/[^\s`|,;)>\]#]+\.md")
_LINE_RANGE_RES = (
    re.compile(r"(?<![\w-])L(\d+)(?:-L?(\d+))?(?!\w)"),
    re.compile(r"\blines? (\d+)(?:-(\d+))?\b", re.IGNORECASE),
)
_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_SIGNAL_RANK: dict[SessionSignal, int] = {
    "correction": 0,
    "decision": 1,
    "unresolved_error_direction_change": 2,
    "none": 3,
}


@dataclass(frozen=True)
class L1Note:
    """One Claude Code auto-memory note. ``path`` is how the reader shows it; ``sha256`` is of its bytes."""

    path: str
    sha256: str
    text: str


@dataclass(frozen=True)
class SessionExchange:
    """One indexed session exchange. ``session`` groups exchanges of one session; empty means ``path``."""

    parent_key: str
    path: str
    line_start: int
    line_end: int
    started_at: datetime
    human_text: str
    outcome: str = ""
    exchange_id: str | None = None
    session: str = ""


@dataclass(frozen=True)
class WikiPageText:
    """A Vault page path (relative to the Vault root) and its whole text, frontmatter included."""

    path: str
    text: str


@dataclass(frozen=True)
class MemoryPage:
    """An indexed Vault page for the merge and retire rules. ``text`` is its body, frontmatter left out."""

    vault_id: str
    path: str
    title: str
    frontmatter: Mapping[str, object]
    vault_scope: VaultProjectScope
    text: str = ""
    evidence_date: str | None = None

    @property
    def key(self) -> PageKey:
        return (self.vault_id, self.path)


@dataclass(frozen=True)
class SimilarPage:
    """A page the finder ranked as similar, with what the project scope rule and the material need."""

    vault_id: str
    path: str
    title: str
    frontmatter: Mapping[str, object]
    vault_scope: VaultProjectScope
    evidence_date: str | None = None


class SimilarPageFinder(Protocol):
    """Pages similar to ``query``, best first, retired pages included, at most ``limit``. Deterministic."""

    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]: ...


@dataclass(frozen=True)
class ComparisonPage:
    vault_id: str
    path: str
    title: str
    status: str | None
    superseded_by: str | None
    retired_reason: str | None
    evidence_date: str | None

    @property
    def label(self) -> str | None:
        """``폐기됨: <이유>`` for a retired, deprecated or superseded page (§4.4.13-2), else None."""
        if self.status not in RETIRED_LABEL_STATUSES:
            return None
        return f"폐기됨: {self.retired_reason or self.status}"


@dataclass(frozen=True)
class MemoryCandidate:
    """One cleanup candidate.

    ``location`` is the L1 note path, the exchange location to cite, the two page paths of a merge
    pair (``<path1> | <path2>``) or the page path to retire. ``targets`` are the pages a merge or
    retire candidate is about. ``similarity`` is the merge cosine similarity. ``reasons`` are the
    retire reasons in Korean, one per ``retire_signals`` item.
    """

    key: str
    kind: CandidateKind
    location: str
    comparison: tuple[ComparisonPage, ...]
    signal: SessionSignal | None = None
    started_at: datetime | None = None
    targets: tuple[ComparisonPage, ...] = ()
    similarity: float | None = None
    retire_signals: tuple[RetireSignal, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Pending:
    key: str
    kind: CandidateKind
    location: str
    query: str
    signal: SessionSignal | None = None
    started_at: datetime | None = None
    targets: tuple[ComparisonPage, ...] = ()
    similarity: float | None = None
    retire_signals: tuple[RetireSignal, ...] = ()
    reasons: tuple[str, ...] = ()
    excluded: frozenset[PageKey] = frozenset()
    # Fixed comparison material (the brief candidate's new decisions); None means a similarity search.
    material: tuple[ComparisonPage, ...] | None = None


def build_memory_candidates(
    *,
    project_id: str | None,
    l1_notes: Iterable[L1Note],
    imported_raw_sha256: Collection[str],
    exchanges: Iterable[SessionExchange],
    wiki_pages: Iterable[WikiPageText],
    reviewed_keys: Collection[str],
    similar_pages: SimilarPageFinder,
    now: datetime,
    limit: int | None = None,
    memory_pages: Iterable[MemoryPage] = (),
    page_vectors: Mapping[PageKey, Sequence[float]] | None = None,
    missing_code: Mapping[PageKey, Sequence[str]] | None = None,
    usage_events: Iterable[Mapping[str, object]] = (),
    kinds: Collection[CandidateKind] | None = None,
    merge_threshold: float = DEFAULT_MERGE_SIMILARITY,
    with_comparison: bool = True,
    brief: ProjectBriefStaleness | None = None,
) -> tuple[MemoryCandidate, ...]:
    """Candidates in table order (L1 notes, session exchanges, merge pairs, retire pages, brief), cut to ``limit``.

    L1 notes are ordered by path, session exchanges by signal, merge pairs by similarity and retire
    pages by signal. ``kinds`` keeps only those kinds; None keeps all. Comparison material is looked
    up only for the candidates returned. ``with_comparison=False`` never calls ``similar_pages`` and
    leaves every ``comparison`` empty: the candidates and their order stay the same (the session start
    backlog line only counts them).
    """
    wanted = frozenset(CANDIDATE_KINDS if kinds is None else kinds)
    pages = tuple(memory_pages)
    pending: list[_Pending] = []
    if "l1_note" in wanted:
        pending.extend(_l1_candidates(l1_notes, imported_raw_sha256, reviewed_keys))
    if "session_exchange" in wanted:
        pending.extend(_session_candidates(exchanges, wiki_pages, reviewed_keys, now))
    if "merge" in wanted:
        pending.extend(_merge_candidates(pages, page_vectors or {}, project_id, reviewed_keys, merge_threshold))
    if "retire" in wanted:
        pending.extend(_retire_candidates(pages, missing_code or {}, usage_events, project_id, reviewed_keys, now))
    if "brief" in wanted and brief is not None:
        pending.extend(_brief_candidates(brief, reviewed_keys))
    if limit is not None:
        pending = pending[: max(limit, 0)]
    return tuple(
        MemoryCandidate(
            key=item.key,
            kind=item.kind,
            location=item.location,
            comparison=_material(item, similar_pages, project_id) if with_comparison else (),
            signal=item.signal,
            started_at=item.started_at,
            targets=item.targets,
            similarity=item.similarity,
            retire_signals=item.retire_signals,
            reasons=item.reasons,
        )
        for item in pending
    )


def is_current_memory_page(page: MemoryPage, project_id: str | None) -> bool:
    """A ``wiki/`` memory page in the project scope that recall would still show (status not stale)."""
    frontmatter = page.frontmatter
    return (
        page.path.startswith("wiki/")
        and _text(frontmatter.get("type")) not in NON_MEMORY_PAGE_TYPES
        and _text(frontmatter.get("status")) not in NOT_CURRENT_STATUSES
        and page_in_project(frontmatter, project_id, vault_scope=page.vault_scope)
    )


def exchange_location(path: str, line_start: int, line_end: int) -> str:
    """The exchange location vg shows and asks agents to cite: ``<path> L<first>-L<last>``."""
    return f"{path} L{line_start}-L{line_end}"


def _l1_candidates(notes: Iterable[L1Note], imported: Collection[str], reviewed: Collection[str]) -> list[_Pending]:
    seen: set[str] = set()
    pending: list[_Pending] = []
    for note in sorted(notes, key=lambda item: (item.path, item.sha256)):
        key = f"{L1_KEY_PREFIX}{note.sha256}"
        if note.path.rsplit("/", 1)[-1] == L1_INDEX_NAME or note.sha256 in imported or key in seen:
            continue
        seen.add(key)
        if key not in reviewed:
            pending.append(_Pending(key=key, kind="l1_note", location=note.path, query=note.text))
    return pending


def _session_candidates(
    exchanges: Iterable[SessionExchange],
    wiki_pages: Iterable[WikiPageText],
    reviewed: Collection[str],
    now: datetime,
) -> list[_Pending]:
    unique = {item.parent_key: item for item in sorted(exchanges, key=_exchange_order, reverse=True)}
    ordered = sorted(unique.values(), key=_exchange_order)
    citations = _exchange_citations(wiki_pages)
    signals = _signals(ordered)
    oldest = now - SESSION_CANDIDATE_MAX_AGE
    pending: list[_Pending] = []
    for exchange in ordered:
        key = f"{SESSION_KEY_PREFIX}{exchange.parent_key}"
        if exchange.started_at < oldest or key in reviewed or _is_cited(exchange, citations):
            continue
        pending.append(
            _Pending(
                key=key,
                kind="session_exchange",
                location=exchange_location(exchange.path, exchange.line_start, exchange.line_end),
                query=exchange.human_text,
                signal=signals[exchange.parent_key],
                started_at=exchange.started_at,
            )
        )
    pending.sort(key=lambda item: item.key)
    pending.sort(key=lambda item: item.started_at or now, reverse=True)
    pending.sort(key=lambda item: _SIGNAL_RANK[item.signal or "none"])
    return pending


def _exchange_order(exchange: SessionExchange) -> tuple[str, datetime, str, int, str]:
    return (
        exchange.session or exchange.path,
        exchange.started_at,
        exchange.path,
        exchange.line_start,
        exchange.parent_key,
    )


def _signals(ordered: Sequence[SessionExchange]) -> dict[str, SessionSignal]:
    """Signal per parent key. ``ordered`` is sorted by session, then time, so the next item is the next exchange."""
    signals: dict[str, SessionSignal] = {}
    for index, exchange in enumerate(ordered):
        text = exchange.human_text.casefold()
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if _has_any(text, CORRECTION_SIGNALS):
            signals[exchange.parent_key] = "correction"
        elif _has_any(text, DECISION_WORDS):
            signals[exchange.parent_key] = "decision"
        elif (
            exchange.outcome == TOOL_ERROR_UNRESOLVED
            and following is not None
            and (following.session or following.path) == (exchange.session or exchange.path)
            and _has_any(following.human_text.casefold(), DIRECTION_CHANGE_WORDS)
        ):
            signals[exchange.parent_key] = "unresolved_error_direction_change"
        else:
            signals[exchange.parent_key] = "none"
    return signals


def _has_any(text: str, words: Sequence[str]) -> bool:
    return any(word in text for word in words)


@dataclass(frozen=True)
class _Citations:
    line_ranges: dict[str, list[tuple[int, int]]]
    id_tokens: dict[str, set[str]]


def _exchange_citations(wiki_pages: Iterable[WikiPageText]) -> _Citations:
    line_ranges: dict[str, list[tuple[int, int]]] = {}
    id_tokens: dict[str, set[str]] = {}
    for page in wiki_pages:
        if not page.path.startswith("wiki/"):
            continue
        for line in page.text.splitlines():
            matches = list(_SESSION_PATH_RE.finditer(line))
            for position, match in enumerate(matches):
                end = matches[position + 1].start() if position + 1 < len(matches) else len(line)
                tail = line[match.end() : end]
                path = match.group(0)
                for pattern in _LINE_RANGE_RES:
                    for found in pattern.finditer(tail):
                        first = int(found.group(1))
                        last = int(found.group(2)) if found.group(2) else first
                        line_ranges.setdefault(path, []).append((min(first, last), max(first, last)))
                id_tokens.setdefault(path, set()).update(_ID_TOKEN_RE.findall(tail))
    return _Citations(line_ranges=line_ranges, id_tokens=id_tokens)


def _is_cited(exchange: SessionExchange, citations: _Citations) -> bool:
    for first, last in citations.line_ranges.get(exchange.path, ()):
        if first <= exchange.line_end and exchange.line_start <= last:
            return True
    exchange_id = exchange.exchange_id
    if not exchange_id:
        return False
    tokens = citations.id_tokens.get(exchange.path, set())
    return exchange_id in tokens or exchange_id[:8] in tokens


def _merge_candidates(
    pages: Sequence[MemoryPage],
    vectors: Mapping[PageKey, Sequence[float]],
    project_id: str | None,
    reviewed: Collection[str],
    threshold: float,
) -> list[_Pending]:
    eligible = sorted(
        (page for page in pages if page.key in vectors and is_current_memory_page(page, project_id)),
        key=lambda page: (page.path, page.vault_id),
    )
    units = {page.key: _unit(vectors[page.key]) for page in eligible}
    pending: list[_Pending] = []
    seen: set[str] = set()
    for index, first in enumerate(eligible):
        first_unit = units[first.key]
        if first_unit is None:
            continue
        for second in eligible[index + 1 :]:
            second_unit = units[second.key]
            if second_unit is None or len(second_unit) != len(first_unit):
                continue
            similarity = round(sum(a * b for a, b in zip(first_unit, second_unit, strict=True)), 6)
            key = f"{MERGE_KEY_PREFIX}{first.path}|{second.path}"
            if similarity < threshold or key in reviewed or key in seen:
                continue
            seen.add(key)
            pending.append(
                _Pending(
                    key=key,
                    kind="merge",
                    location=f"{first.path} | {second.path}",
                    query=_page_query(first),
                    targets=(_comparison_page(first), _comparison_page(second)),
                    similarity=similarity,
                    excluded=frozenset({first.key, second.key}),
                )
            )
    pending.sort(key=lambda item: item.key)
    pending.sort(key=lambda item: item.similarity or 0.0, reverse=True)
    return pending


def _unit(vector: Sequence[float]) -> tuple[float, ...] | None:
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return None
    return tuple(value / norm for value in vector)


def _retire_candidates(
    pages: Sequence[MemoryPage],
    missing_code: Mapping[PageKey, Sequence[str]],
    usage_events: Iterable[Mapping[str, object]],
    project_id: str | None,
    reviewed: Collection[str],
    now: datetime,
) -> list[_Pending]:
    injected = _unused_injections(usage_events, now)
    pending: list[_Pending] = []
    seen: set[str] = set()
    for page in sorted(pages, key=lambda item: (item.path, item.vault_id)):
        key = f"{RETIRE_KEY_PREFIX}{page.path}"
        if key in reviewed or key in seen or page.frontmatter.get("pin") is True:
            continue
        if not is_current_memory_page(page, project_id):
            continue
        signals: list[RetireSignal] = []
        reasons: list[str] = []
        gone = sorted(set(missing_code.get(page.key, ())))
        if gone:
            signals.append("code_gone")
            reasons.append(f"근거 코드가 등록 저장소에서 사라짐: {', '.join(gone)}")
        count = injected.get(page.key, 0)
        if count:
            signals.append("unused")
            reasons.append(f"최근 {RETIRE_UNUSED_WINDOW.days}일 회상 주입 {count}회, 열람 0회")
        if not signals:
            continue
        seen.add(key)
        pending.append(
            _Pending(
                key=key,
                kind="retire",
                location=page.path,
                query=_page_query(page),
                targets=(_comparison_page(page),),
                retire_signals=tuple(signals),
                reasons=tuple(reasons),
                excluded=frozenset({page.key}),
            )
        )
    pending.sort(key=lambda item: item.retire_signals[0] != "code_gone")
    return pending


def _brief_candidates(brief: ProjectBriefStaleness, reviewed: Collection[str]) -> list[_Pending]:
    staleness = brief.staleness
    if not staleness.stale or brief.key in reviewed:
        return []
    current = staleness.brief
    count = staleness.count
    reason = f"brief 이후 새 결정 {count}개" if current is not None else f"brief 없음, 결정 {count}개"
    return [
        _Pending(
            key=brief.key,
            kind="brief",
            location=brief.brief_path,
            query="",
            targets=(_document_comparison_page(current),) if current is not None else (),
            reasons=(reason,),
            material=tuple(_document_comparison_page(document) for document in staleness.new_decisions),
        )
    ]


def _document_comparison_page(document: DocumentSnapshot) -> ComparisonPage:
    frontmatter = document.frontmatter
    title = _text(frontmatter.get("title")) or document.path.rsplit("/", 1)[-1].removesuffix(".md")
    return ComparisonPage(
        vault_id=document.vault_id,
        path=document.path,
        title=title,
        status=_text(frontmatter.get("status")),
        superseded_by=_text(frontmatter.get("superseded_by")),
        retired_reason=_text(frontmatter.get("retired_reason")),
        evidence_date=next(
            (text for name in ("updated", "created", "date") if (text := _text(frontmatter.get(name)))), None
        ),
    )


def _material(item: _Pending, finder: SimilarPageFinder, project_id: str | None) -> tuple[ComparisonPage, ...]:
    if item.material is not None:
        return item.material
    return _comparison(finder, item.query, project_id, excluded=item.excluded)


def _unused_injections(events: Iterable[Mapping[str, object]], now: datetime) -> dict[PageKey, int]:
    """Injection counts in the window of pages never fetched in it. Empty when the log is younger than the window."""
    start = now - RETIRE_UNUSED_WINDOW
    covered = False
    injected: dict[PageKey, int] = {}
    fetched: set[PageKey] = set()
    for event in events:
        at = _event_time(event.get("at"))
        if at is None:
            continue
        if at <= start:
            covered = True
            continue
        if at > now:
            continue
        vault_id, path = event.get("vault_id"), event.get("path")
        if not isinstance(vault_id, str) or not isinstance(path, str):
            continue
        if event.get("event") == "injected":
            injected[(vault_id, path)] = injected.get((vault_id, path), 0) + 1
        elif event.get("event") == "fetched":
            fetched.add((vault_id, path))
    if not covered:
        return {}
    return {key: count for key, count in injected.items() if key not in fetched}


def _event_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _page_query(page: MemoryPage) -> str:
    return f"{page.title}\n\n{page.text}".strip()


def _comparison_page(page: MemoryPage | SimilarPage) -> ComparisonPage:
    return ComparisonPage(
        vault_id=page.vault_id,
        path=page.path,
        title=page.title,
        status=_text(page.frontmatter.get("status")),
        superseded_by=_text(page.frontmatter.get("superseded_by")),
        retired_reason=_text(page.frontmatter.get("retired_reason")),
        evidence_date=page.evidence_date,
    )


def _comparison(
    finder: SimilarPageFinder, query: str, project_id: str | None, *, excluded: Collection[PageKey] = ()
) -> tuple[ComparisonPage, ...]:
    if not query.strip():
        return ()
    material: list[ComparisonPage] = []
    for page in finder.find_similar(query, limit=COMPARISON_FETCH_LIMIT):
        if (page.vault_id, page.path) in excluded:
            continue
        if not page_in_project(page.frontmatter, project_id, vault_scope=page.vault_scope):
            continue
        material.append(_comparison_page(page))
        if len(material) == COMPARISON_PAGE_LIMIT:
            break
    return tuple(material)


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "CANDIDATE_KINDS",
    "COMPARISON_PAGE_LIMIT",
    "CORRECTION_SIGNALS",
    "DECISION_WORDS",
    "DEFAULT_MERGE_SIMILARITY",
    "DIRECTION_CHANGE_WORDS",
    "MERGE_KEY_PREFIX",
    "RETIRE_KEY_PREFIX",
    "RETIRE_UNUSED_WINDOW",
    "SESSION_CANDIDATE_MAX_AGE",
    "CandidateKind",
    "ComparisonPage",
    "L1Note",
    "MemoryCandidate",
    "MemoryPage",
    "PageKey",
    "RetireSignal",
    "SessionExchange",
    "SessionSignal",
    "SimilarPage",
    "SimilarPageFinder",
    "WikiPageText",
    "build_memory_candidates",
    "exchange_location",
    "is_current_memory_page",
]
