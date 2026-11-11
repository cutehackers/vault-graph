"""Scoring of the search evaluation tool (spec 2026-11-11 §4.1.2).

Matching reuses the two measurement tools. An expected exchange matches a result or a chunk the way
`measure_session_recall` does: same path and an overlapping line range of an evidence locator. An expected
page matches the way `measure_memory_recall` does: same (Vault id, Vault-relative path). recall@k and MRR use
the `measure_session_recall` formulas over the scored questions: a hit is a first rank at or above k, and MRR
is the sum of 1/first rank over the scored questions, with ranks read from the first ``RESULT_LIMIT`` results.

Each scored question falls in one class:

- hit (적중): the first matching result is in the top ``HIT_LIMIT``.
- rank_loss (순위 손실): not a hit, but a matching chunk is in some signal's candidate list.
- candidate_loss (후보 손실): no signal's candidate list holds a matching chunk.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from tests.benchmarks import measure_memory_recall as memory_tool
from tests.benchmarks import measure_session_recall as session_tool
from tests.benchmarks.eval_dataset import KINDS, EvalQuestion
from vault_graph.indexing.ingestion.document_models import SourceLocator
from vault_graph.retrieval.search.retrieval_result import RetrievalResult
from vault_graph.retrieval.search.search_response import SearchStageTrace

RESULT_LIMIT = session_tool.RESULT_LIMIT
HIT_LIMIT = 5
OUTCOMES = ("hit", "rank_loss", "candidate_loss")
SIGNAL_KINDS = ("keyword", "vector", "graph")

PageKey = tuple[str, str]  # (Graph Home Vault id, Vault-relative path)
Span = tuple[str, int, int]  # (path, first line, last line)


@dataclass(frozen=True)
class Target:
    """A search result or an indexed chunk reduced to what matching needs."""

    pages: tuple[PageKey, ...]
    spans: tuple[Span, ...]


@dataclass(frozen=True)
class Expected:
    pages: frozenset[PageKey]
    exchanges: tuple[session_tool.ExchangeLocation, ...]

    def matches(self, target: Target) -> bool:
        if any(page in self.pages for page in target.pages):
            return True
        return session_tool.first_rank(self.exchanges, (session_tool.ResultUnit(target.spans, False),)) == 1


@dataclass(frozen=True)
class StageRanks:
    """Best rank of a matching chunk or result at each search stage; None when no entry matches."""

    keyword: int | None
    vector: int | None
    graph: int | None
    fused: int | None
    document: int | None

    @property
    def in_candidates(self) -> bool:
        return any(rank is not None for rank in (self.keyword, self.vector, self.graph))


@dataclass(frozen=True)
class QuestionScore:
    question_id: str
    kind: str
    split: str
    scored: bool
    final_rank: int | None
    ranks: StageRanks | None
    seconds: float
    error: str | None

    @property
    def outcome(self) -> str | None:
        if self.error is not None or not self.scored:
            return None
        if self.final_rank is not None and self.final_rank <= HIT_LIMIT:
            return "hit"
        if self.ranks is not None and self.ranks.in_candidates:
            return "rank_loss"
        return "candidate_loss"

    def to_json(self) -> dict[str, object]:
        ranks = self.ranks
        return {
            "id": self.question_id,
            "kind": self.kind,
            "split": self.split,
            "scored": self.scored,
            "final_rank": self.final_rank,
            "keyword_rank": ranks.keyword if ranks else None,
            "vector_rank": ranks.vector if ranks else None,
            "graph_rank": ranks.graph if ranks else None,
            "fused_rank": ranks.fused if ranks else None,
            "document_rank": ranks.document if ranks else None,
            "outcome": self.outcome,
            "seconds": round(self.seconds, 3),
            "error": self.error,
        }


def expected_for(question: EvalQuestion, *, vault_ids: Iterable[str]) -> Expected:
    """Resolve expected pages against the Graph Home Vault ids. An unknown Vault raises ValueError."""
    known = frozenset(vault_ids)
    keys = memory_tool.resolve_expected(question.pages, resolve=lambda label: label if label in known else None)
    return Expected(pages=frozenset(keys), exchanges=question.exchanges)


def evidence_spans(path: str, locators: Sequence[SourceLocator]) -> tuple[Span, ...]:
    """Line spans of one evidence item, read with the `measure_session_recall` locator rule."""
    payload = {"results": [{"evidence": [{"path": path, "source_locators": [item.to_dict() for item in locators]}]}]}
    return session_tool.result_units(payload)[0].spans


def result_target(result: RetrievalResult) -> Target:
    pages: dict[PageKey, None] = {}
    spans: list[Span] = []
    for evidence in result.evidence:
        pages.setdefault((evidence.vault_id, evidence.path), None)
        spans.extend(evidence_spans(evidence.path, evidence.source_locators))
    return Target(pages=tuple(pages), spans=tuple(spans))


def first_rank(expected: Expected, results: Sequence[Target]) -> int | None:
    """1-based rank of the first result that matches an expected page or exchange, or None."""
    return next((rank for rank, target in enumerate(results, start=1) if expected.matches(target)), None)


def stage_ranks(
    expected: Expected,
    trace: SearchStageTrace,
    *,
    chunk_target: Callable[[str, str], Target | None],
    final_rank: int | None,
) -> StageRanks:
    """Best rank of a matching chunk in each signal list and the fused list, and of a matching document.

    ``chunk_target`` resolves (Vault id, chunk id) to the chunk's path and line spans. A document entry has
    no line spans, so an expected exchange reaches the document stage only through ``final_rank``.
    """

    def best(ranks: Iterable[int]) -> int | None:
        return min(ranks, default=None)

    def matching(vault_id: str, chunk_id: str) -> bool:
        target = chunk_target(vault_id, chunk_id)
        return target is not None and expected.matches(target)

    signal = {
        kind: best(
            entry.rank
            for entry in trace.signal_ranks
            if entry.kind == kind and matching(entry.vault_id, entry.chunk_id)
        )
        for kind in SIGNAL_KINDS
    }
    fused = best(entry.rank for entry in trace.fused_ranks if matching(entry.vault_id, entry.chunk_id))
    document = best(
        [
            *(entry.rank for entry in trace.document_ranks if (entry.vault_id, entry.path) in expected.pages),
            *([final_rank] if final_rank is not None else []),
        ]
    )
    return StageRanks(signal["keyword"], signal["vector"], signal["graph"], fused, document)


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least ``fraction`` of the values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(fraction * len(ordered)), 1) - 1]


def summarize(scores: Sequence[QuestionScore]) -> dict[str, object]:
    """Totals and per-kind scores. Holds no question text."""
    measured = [score for score in scores if score.error is None]
    seconds = [score.seconds for score in measured]
    p50, p95 = percentile(seconds, 0.5), percentile(seconds, 0.95)
    return {
        **_block(scores),
        "by_kind": {
            kind: _block(rows) for kind in KINDS if (rows := [score for score in scores if score.kind == kind])
        },
        "seconds": {
            "p50": round(p50, 3) if p50 is not None else None,
            "p95": round(p95, 3) if p95 is not None else None,
        },
        "result_limit": RESULT_LIMIT,
        "hit_limit": HIT_LIMIT,
    }


def _block(scores: Sequence[QuestionScore]) -> dict[str, object]:
    scored = [score for score in scores if score.error is None and score.scored]

    def recall(limit: int) -> float | None:
        if not scored:
            return None
        hits = sum(1 for row in scored if row.final_rank is not None and row.final_rank <= limit)
        return round(hits / len(scored), 4)

    def mrr() -> float | None:
        if not scored:
            return None
        return round(sum(1.0 / row.final_rank for row in scored if row.final_rank is not None) / len(scored), 4)

    return {
        "questions": len(scores),
        "failed": sum(1 for score in scores if score.error is not None),
        "scored": len(scored),
        "recall_at_5": recall(5),
        "recall_at_10": recall(10),
        "mrr": mrr(),
        "outcomes": {outcome: sum(1 for row in scored if row.outcome == outcome) for outcome in OUTCOMES},
    }
