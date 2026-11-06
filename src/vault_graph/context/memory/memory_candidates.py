"""Cleanup candidates for L1 notes and session exchanges (spec 2026-11-05 §4.4.4, A-22, A-38).

The cleanup bundle is deterministic: the same index, the same L1 notes, the same Vault pages and
the same review records give the same result. No LLM runs here. The calling agent decides what
to remember. Callers (composition) read the inputs and pass them in:

- L1 notes as ``L1Note`` and the ``raw_sha256`` values of the Vault's ``raw/imports/claude-memory/``
  copies. A note whose sha256 is among them is already kept. ``MEMORY.md`` is the L1 index, not a note.
- Indexed session exchanges as ``SessionExchange`` (one per ``parent_key`` of the v1/v2 session chunkers).
- Vault pages as ``WikiPageText``. Only ``wiki/`` pages count as citing an exchange.
- Candidate keys already recorded in the Graph Home ``memory/reviewed.jsonl``.
- A ``SimilarPageFinder`` for comparison material.

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
from typing import Literal, Protocol

from vault_graph.context.memory.project_scope import VaultProjectScope, page_in_project

SESSION_CANDIDATE_MAX_AGE = timedelta(days=180)
COMPARISON_PAGE_LIMIT = 5
COMPARISON_FETCH_LIMIT = 20
L1_INDEX_NAME = "MEMORY.md"
L1_KEY_PREFIX = "l1:"
SESSION_KEY_PREFIX = "session:"
TOOL_ERROR_UNRESOLVED = "tool_error_unresolved"

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

CandidateKind = Literal["l1_note", "session_exchange"]
SessionSignal = Literal["correction", "decision", "unresolved_error_direction_change", "none"]

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


@dataclass(frozen=True)
class MemoryCandidate:
    """One cleanup candidate. ``location`` is the L1 note path or the exchange location to cite."""

    key: str
    kind: CandidateKind
    location: str
    comparison: tuple[ComparisonPage, ...]
    signal: SessionSignal | None = None
    started_at: datetime | None = None


@dataclass(frozen=True)
class _Pending:
    key: str
    kind: CandidateKind
    location: str
    query: str
    signal: SessionSignal | None = None
    started_at: datetime | None = None


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
) -> tuple[MemoryCandidate, ...]:
    """L1 note candidates by path, then session exchange candidates in signal order, cut to ``limit``.

    Comparison material is looked up only for the candidates returned.
    """
    pending = [
        *_l1_candidates(l1_notes, imported_raw_sha256, reviewed_keys),
        *_session_candidates(exchanges, wiki_pages, reviewed_keys, now),
    ]
    if limit is not None:
        pending = pending[: max(limit, 0)]
    return tuple(
        MemoryCandidate(
            key=item.key,
            kind=item.kind,
            location=item.location,
            comparison=_comparison(similar_pages, item.query, project_id),
            signal=item.signal,
            started_at=item.started_at,
        )
        for item in pending
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


def _comparison(finder: SimilarPageFinder, query: str, project_id: str | None) -> tuple[ComparisonPage, ...]:
    if not query.strip():
        return ()
    material: list[ComparisonPage] = []
    for page in finder.find_similar(query, limit=COMPARISON_FETCH_LIMIT):
        if not page_in_project(page.frontmatter, project_id, vault_scope=page.vault_scope):
            continue
        material.append(
            ComparisonPage(
                vault_id=page.vault_id,
                path=page.path,
                title=page.title,
                status=_text(page.frontmatter.get("status")),
                superseded_by=_text(page.frontmatter.get("superseded_by")),
                retired_reason=_text(page.frontmatter.get("retired_reason")),
                evidence_date=page.evidence_date,
            )
        )
        if len(material) == COMPARISON_PAGE_LIMIT:
            break
    return tuple(material)


def _text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "COMPARISON_PAGE_LIMIT",
    "CORRECTION_SIGNALS",
    "DECISION_WORDS",
    "DIRECTION_CHANGE_WORDS",
    "SESSION_CANDIDATE_MAX_AGE",
    "CandidateKind",
    "ComparisonPage",
    "L1Note",
    "MemoryCandidate",
    "SessionExchange",
    "SessionSignal",
    "SimilarPage",
    "SimilarPageFinder",
    "WikiPageText",
    "build_memory_candidates",
    "exchange_location",
]
