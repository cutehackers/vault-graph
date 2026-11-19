"""Did facts from waiting session exchanges become memory, and does a context pack find them? (spec 2026-11-19 §7, C8)

The questions are written BEFORE dreaming runs, from session exchanges that no memory page cites yet, so they do
not depend on what a dream run chooses to propose. Run it before the first dream run and again after proposals
were accepted and indexed:

  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.measure_dream_backlog \
    --questions <questions.jsonl> --graph-home <graph home> --vault-map <vault-map.json> --out-dir <out dir>

The question file and out_dir must be outside this repository: the questions hold personal content. Each line is
`{"id": str, "question": str, "cwd": str, "expected_exchanges": ["<path> L<a>-L<b>", ...]}`. `cwd` is the absolute
project folder. `expected_exchanges` are the session exchange locations that hold the answer, as
`list_memory_candidates` shows them.

Per question, with no language model:

- `remembered`: some `wiki/` page of a Vault linked to the project cites one of the expected exchanges (the same
  path and an overlapping line range). Before dreaming this must be false for every question, or the question
  is not a backlog-only question.
- `context_hit`: the MCP tool `build_context_pack`, run with the question as goal, returns such a page as
  evidence.

`out_dir/results.jsonl` holds one row per question (id and the two flags) and `out_dir/summary.json` the totals.
Neither holds question text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.benchmarks.measure_memory_recall import (
    Question,
    _context_pack,
    _repository_commit,
    _require_outside_repository,
    _write_lines,
)
from vault_graph.operation.memory.evidence_quote import ExchangeCitation, cited_exchanges

# Any axis the recall harness knows. The context pack call does not use it.
_AXIS = "정보 추출"


@dataclass(frozen=True)
class BacklogQuestion:
    question_id: str
    text: str
    cwd: Path
    expected: tuple[ExchangeCitation, ...]


def load_backlog_questions(path: Path) -> tuple[BacklogQuestion, ...]:
    questions: list[BacklogQuestion] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: a question must be a JSON object")
        question_id, text, cwd, expected = (
            row.get("id"),
            row.get("question"),
            row.get("cwd"),
            row.get("expected_exchanges"),
        )
        if not isinstance(question_id, str) or not question_id or not isinstance(text, str) or not text.strip():
            raise ValueError(f"line {number}: id and question must be non-empty strings")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError(f"line {number}: cwd must be an absolute project folder")
        if not isinstance(expected, list) or not expected or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"line {number}: expected_exchanges must list at least one '<path> L<a>-L<b>'")
        citations = cited_exchanges(expected)
        if len(citations) != len(expected):
            raise ValueError(f"line {number}: every expected exchange must be '<raw/sessions path> L<a>-L<b>'")
        if question_id in seen:
            raise ValueError(f"line {number}: duplicate id {question_id!r}")
        seen.add(question_id)
        questions.append(BacklogQuestion(question_id, text, Path(cwd), citations))
    return tuple(questions)


def cites_expected(page_text: str, expected: Sequence[ExchangeCitation]) -> bool:
    """True when the page cites one of the expected exchanges: the same file and an overlapping line range."""
    return any(
        cited.path == wanted.path and cited.line_start <= wanted.line_end and wanted.line_start <= cited.line_end
        for cited in cited_exchanges(page_text.splitlines())
        for wanted in expected
    )


def citing_pages(vault_roots: Sequence[Path], expected: Sequence[ExchangeCitation]) -> tuple[tuple[Path, str], ...]:
    """`(vault root, page path)` of every `wiki/` page of the Vaults that cites an expected exchange."""
    found: list[tuple[Path, str]] = []
    for root in vault_roots:
        wiki = root / "wiki"
        if not wiki.is_dir():
            continue
        for page in sorted(wiki.rglob("*.md")):
            try:
                text = page.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if cites_expected(text, expected):
                found.append((root, page.relative_to(root).as_posix()))
    return tuple(found)


def summarize(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    scored = [row for row in rows if row.get("error") is None]
    remembered = sum(1 for row in scored if row["remembered"])
    hits = sum(1 for row in scored if row["context_hit"])
    return {
        "questions": len(rows),
        "errors": len(rows) - len(scored),
        "remembered": remembered,
        "context_hit": hits,
        "remembered_rate": round(remembered / len(scored), 2) if scored else None,
        "context_hit_rate": round(hits / len(scored), 2) if scored else None,
    }


def main(questions: Path, *, graph_home: Path, vault_map: Path, out_dir: Path) -> dict[str, object]:
    from vault_graph.operation.integration.vault_map import open_vault_map
    from vault_graph.operation.scope.catalog_service import CatalogService

    _require_outside_repository(questions, "questions")
    _require_outside_repository(out_dir, "out_dir")
    loaded = load_backlog_questions(questions)
    opened = open_vault_map(vault_map).vault_map
    if opened is None:
        raise ValueError(f"no usable vault-map.json at {vault_map}")
    catalog = CatalogService(graph_home_path=graph_home).load_catalog()
    rows: list[dict[str, object]] = []
    for question in loaded:
        roots = [vault.path for vault in opened.vaults_for(question.cwd)]
        citing = citing_pages(roots, question.expected)
        row: dict[str, object] = {
            "id": question.question_id,
            "remembered": bool(citing),
            "context_hit": False,
            "error": None,
        }
        try:
            evidence = _context_pack(
                Question(question.question_id, question.text, question.cwd, (), _AXIS),
                graph_home=graph_home,
                vault_map=vault_map,
            )
            wanted = {(root.resolve(), path) for root, path in citing}
            row["context_hit"] = any(
                (catalog.resolve(vault_id).root_path.resolve(), path) in wanted for vault_id, path in evidence
            )
        except Exception as exc:  # one failed question is reported in its row, the others still run
            row["error"] = " ".join(str(exc).split())[:300]
        rows.append(row)
    summary = summarize(rows)
    summary["commit"] = _repository_commit()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_lines(out_dir / "results.jsonl", rows)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "utf-8"
    )
    return summary


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--graph-home", type=Path, required=True)
    parser.add_argument("--vault-map", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    result = main(
        arguments.questions, graph_home=arguments.graph_home, vault_map=arguments.vault_map, out_dir=arguments.out_dir
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
