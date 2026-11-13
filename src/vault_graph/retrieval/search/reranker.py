"""Cross-encoder reranking of the top search results (spec 2026-11-13 cross-encoder-rerank D6·D8).

The port `Reranker` orders passages for a query. `rerank_results` mixes that order with the search order by
reciprocal rank fusion and renumbers the results. It only reorders: no result is added or dropped, and
nothing is written anywhere (I1, I4).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from vault_graph.errors import VaultGraphError
from vault_graph.retrieval.search.retrieval_result import RetrievalResult

# Fixed on the layer-1 development questions (spec 2026-11-13 D8, D16), compared with k 10 and weights 0.5 and 2:
# docs/design/reports/2026-11-reranker-measurement.md §8.
RERANK_DEPTH = 30
RRF_K = 60
RERANK_WEIGHT = 1.0


class RerankError(VaultGraphError):
    """The reranking model could not order the passages."""


class RerankerUnavailableError(VaultGraphError):
    """The reranking model files are not in the model folder. Search never downloads them (I2)."""


class Reranker(Protocol):
    """Orders passages by relevance to a query with a local model.

    ``preset`` names the model preset, for the search trace.
    """

    @property
    def preset(self) -> str: ...

    def rerank(self, query: str, passages: Sequence[str]) -> list[int]:
        """Indices into ``passages``, most relevant first. Each index appears once. Raises `RerankError`."""
        ...


@dataclass(frozen=True)
class RerankTraceEntry:
    """One reranked result: its rank before reranking, the model's rank, and its final rank and id."""

    result_id: str
    rank: int
    before_rank: int
    model_rank: int


@dataclass(frozen=True)
class RerankTrace:
    """What one reranking did, for the evaluation tool (D13). ``entries`` follow the final order."""

    preset: str
    reranked_count: int
    entries: tuple[RerankTraceEntry, ...]
    elapsed_seconds: float


@dataclass(frozen=True)
class RerankedResults:
    """Results in their final order. ``trace`` is None when the model was not asked."""

    results: tuple[RetrievalResult, ...]
    trace: RerankTrace | None


def rerank_results(
    *,
    query_text: str,
    results: tuple[RetrievalResult, ...],
    passages: tuple[str, ...],
    reranker: Reranker,
) -> RerankedResults:
    """Rerank the top `RERANK_DEPTH` results and renumber all of them.

    ``passages`` holds the reranking text of each result, in result order. Results below the depth keep their
    order after the reranked ones. With one result or none the model is not asked and nothing changes.
    """
    if len(results) <= 1:
        return RerankedResults(results=results, trace=None)
    head = results[:RERANK_DEPTH]
    started = time.perf_counter()
    model_order = reranker.rerank(query_text, list(passages[: len(head)]))
    elapsed = time.perf_counter() - started
    model_ranks = _model_ranks(model_order, count=len(head))
    order = blend_order(model_ranks)
    reordered = renumber_results((*(head[index] for index in order), *results[len(head) :]))
    entries = tuple(
        RerankTraceEntry(
            result_id=reordered[position].result_id,
            rank=position + 1,
            before_rank=index + 1,
            model_rank=model_ranks[index],
        )
        for position, index in enumerate(order)
    )
    return RerankedResults(
        results=reordered,
        trace=RerankTrace(preset=reranker.preset, reranked_count=len(head), entries=entries, elapsed_seconds=elapsed),
    )


def blend_order(model_ranks: Sequence[int], *, k: int = RRF_K, weight: float = RERANK_WEIGHT) -> list[int]:
    """Positions of the results in blended order.

    ``model_ranks[i]`` is the model's rank (from 1) of the result at search rank ``i + 1``. The blended score
    is ``1/(k + search rank) + weight/(k + model rank)``. On equal scores the better search rank goes first.
    """
    scores = [1 / (k + index + 1) + weight / (k + model_rank) for index, model_rank in enumerate(model_ranks)]
    return sorted(range(len(model_ranks)), key=lambda index: (-scores[index], index))


def renumber_results(results: Sequence[RetrievalResult]) -> tuple[RetrievalResult, ...]:
    """Give ``rank`` 1..n in the given order and match the `rank-N` part of each ``result_id`` (I5)."""
    return tuple(
        replace(result, rank=rank, result_id=f"{result.result_id.rsplit(':rank-', 1)[0]}:rank-{rank}")
        for rank, result in enumerate(results, start=1)
    )


def _model_ranks(model_order: Sequence[int], *, count: int) -> list[int]:
    if sorted(model_order) != list(range(count)):
        raise RerankError(f"reranker returned {list(model_order)!r}, not an order of {count} passages")
    ranks = [0] * count
    for rank, index in enumerate(model_order, start=1):
        ranks[index] = rank
    return ranks
