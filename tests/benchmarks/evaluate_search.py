"""Search evaluation: per-kind recall@5, recall@10, MRR, loss table and search time p50/p95 in one process.

Spec 2026-11-11 §4.1.2, A-3. Run from the repository root after `vg index`:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.evaluate_search \
    --questions <questions.json> --graph-home <graph home copy> --out-dir <out dir> [--split dev|test] \
    [--vault-id ID ...] [--include-graph]

The question set format is in `tests/benchmarks/eval_dataset.py`; scoring is in `eval_scoring.py`.

- The tool calls the search service directly in this process with stage tracing, once per question, after
  one untimed warm-up search that loads the embedding model. Search time is the wall time of one
  `RetrievalService.search` call.
- It runs only on a new Graph Home or a copy: the default Graph Home (`~/.vault-graph`) is refused. It opens
  the stores read only and calls the search service, which writes no `usage/` record.
- Layer 1 questions come from a real Vault: their file and `out_dir` must be outside this repository.
- Per-question rows go to `out_dir/results.jsonl` and totals to `out_dir/summary.json`. Neither holds
  question text. The table printed to stdout holds totals only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tests.benchmarks.eval_dataset import SPLITS, EvalQuestion, load_dataset
from tests.benchmarks.eval_scoring import (
    OUTCOMES,
    RESULT_LIMIT,
    QuestionScore,
    Target,
    evidence_spans,
    expected_for,
    first_rank,
    result_target,
    stage_ranks,
    summarize,
)
from vault_graph.errors import VaultGraphError
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.search.search_response import SearchMode, SearchResponse
from vault_graph.storage.interfaces.metadata_store import MetadataStore

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_LAYER = 1
WARM_UP_QUERY = "vault graph search evaluation warm-up"


class SearchService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        include_graph: bool = False,
        mode: SearchMode = "knowledge",
        trace: bool = False,
    ) -> SearchResponse: ...


@dataclass(frozen=True)
class SearchPorts:
    catalog: VaultCatalog
    metadata_store: MetadataStore
    service: SearchService


def evaluate(
    questions: Sequence[EvalQuestion],
    *,
    ports: SearchPorts,
    scope: QueryScope,
    include_graph: bool = False,
    clock: Callable[[], float] = time.perf_counter,
) -> list[QuestionScore]:
    """Search each question once with stage tracing and score it. A failed search is an error row."""
    vault_ids = tuple(entry.vault_id for entry in ports.catalog.entries())
    chunks: dict[tuple[str, str], Target | None] = {}

    def chunk_target(vault_id: str, chunk_id: str) -> Target | None:
        key = (vault_id, chunk_id)
        if key not in chunks:
            chunk = ports.metadata_store.resolve_chunk(vault_id=vault_id, chunk_id=chunk_id)
            chunks[key] = (
                None
                if chunk is None
                else Target(
                    pages=((chunk.vault_id, chunk.path),), spans=evidence_spans(chunk.path, chunk.source_locators)
                )
            )
        return chunks[key]

    scores: list[QuestionScore] = []
    for question in questions:
        started = clock()
        try:
            expected = expected_for(question, vault_ids=vault_ids)
            started = clock()
            response = ports.service.search(
                query_text=question.text,
                requested_scope=scope,
                limit=RESULT_LIMIT,
                include_graph=include_graph,
                mode=question.mode,
                trace=True,
            )
            seconds = clock() - started
            if response.stage_trace is None:
                raise ValueError("search returned no stage trace")
            final = first_rank(expected, [result_target(result) for result in response.results])
            ranks = stage_ranks(expected, response.stage_trace, chunk_target=chunk_target, final_rank=final)
        except (ValueError, VaultGraphError) as exc:
            scores.append(_failed(question, clock() - started, exc))
            continue
        scores.append(
            QuestionScore(
                question.question_id, question.kind, question.split, question.scored, final, ranks, seconds, None
            )
        )
    return scores


def main(
    questions: Path,
    *,
    graph_home: Path,
    out_dir: Path,
    split: str | None = None,
    vault_ids: Sequence[str] = (),
    include_graph: bool = False,
    open_ports: Callable[[Path, bool], SearchPorts] | None = None,
) -> dict[str, object]:
    dataset = load_dataset(questions)
    check_paths(layer=dataset.layer, questions=questions, out_dir=out_dir, graph_home=graph_home)
    selected = dataset.select(split)
    ports = (open_ports or open_search_ports)(graph_home, include_graph)
    scope = ports.catalog.scope_for_vault_ids(list(vault_ids)) if vault_ids else ports.catalog.scope_for_all_enabled()
    _warm_up(ports, scope=scope, include_graph=include_graph)
    scores = evaluate(selected, ports=ports, scope=scope, include_graph=include_graph)
    summary = {
        **summarize(scores),
        "layer": dataset.layer,
        "split": split or "all",
        "include_graph": include_graph,
        "vault_ids": list(scope.vault_ids),
        "commit": _repository_commit(),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_lines(out_dir / "results.jsonl", (score.to_json() for score in scores))
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def check_paths(*, layer: int, questions: Path, out_dir: Path, graph_home: Path) -> None:
    """Refuse the default Graph Home, and layer 1 question files or results inside the repository."""
    if graph_home.expanduser().resolve() == DEFAULT_GRAPH_HOME.expanduser().resolve():
        raise ValueError("graph_home must be a new Graph Home or a copy, not the default Graph Home")
    if layer == PRIVATE_LAYER:
        _require_outside_repository(questions, "questions")
        _require_outside_repository(out_dir, "out_dir")


def open_search_ports(graph_home: Path, include_graph: bool) -> SearchPorts:
    from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory

    factory = ReadOnlyServiceFactory(graph_home_path=graph_home)
    services = factory.open_read_only()
    service = factory.open_retrieval_service(include_graph=True) if include_graph else services.retrieval_service
    return SearchPorts(catalog=services.catalog, metadata_store=services.metadata_store, service=service)


def format_table(summary: Mapping[str, object]) -> str:
    """Per-kind scores, loss table and search time as plain text, totals only."""
    header = ("kind", "questions", "scored", "recall@5", "recall@10", "MRR", *OUTCOMES)
    rows: list[tuple[str, ...]] = [header]
    by_kind = summary.get("by_kind")
    blocks = [*(by_kind.items() if isinstance(by_kind, dict) else ()), ("total", summary)]
    for name, block in blocks:
        outcomes = block.get("outcomes", {})
        rows.append(
            (
                str(name),
                *(_cell(block.get(key)) for key in ("questions", "scored", "recall_at_5", "recall_at_10", "mrr")),
                *(_cell(outcomes.get(outcome)) for outcome in OUTCOMES),
            )
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(header))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows]
    seconds = summary.get("seconds")
    if isinstance(seconds, dict):
        lines.append(f"search seconds: p50 {_cell(seconds.get('p50'))}  p95 {_cell(seconds.get('p95'))}")
    lines.append(f"failed: {_cell(summary.get('failed'))}")
    return "\n".join(lines)


def _warm_up(ports: SearchPorts, *, scope: QueryScope, include_graph: bool) -> None:
    """Load the embedding model before the timed searches, so the first question does not pay for it."""
    try:
        ports.service.search(query_text=WARM_UP_QUERY, requested_scope=scope, limit=1, include_graph=include_graph)
    except VaultGraphError:
        pass


def _failed(question: EvalQuestion, seconds: float, exc: Exception) -> QuestionScore:
    return QuestionScore(
        question.question_id, question.kind, question.split, question.scored, None, None, seconds, str(exc)[:300]
    )


def _cell(value: object) -> str:
    return "-" if value is None else str(value)


def _write_lines(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), "utf-8")


def _require_outside_repository(path: Path, label: str) -> None:
    if path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError(f"{label} must be outside the repository: layer 1 holds personal Vault content")


def _repository_commit() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() or "unknown"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--graph-home", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--split", choices=SPLITS, help="Evaluate one split; all questions when absent.")
    parser.add_argument("--vault-id", action="append", default=[], help="Search these Vaults; all enabled when absent.")
    parser.add_argument("--include-graph", action="store_true", help="Add the graph signal to each search.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    result = main(
        arguments.questions,
        graph_home=arguments.graph_home,
        out_dir=arguments.out_dir,
        split=arguments.split,
        vault_ids=arguments.vault_id,
        include_graph=arguments.include_graph,
    )
    print(format_table(result))
