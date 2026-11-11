"""Question set format of the search evaluation tool (spec 2026-11-11 §4.1.1).

A question set is one JSON document:

    {
      "format": "vg-search-eval/1",
      "layer": 1 | 2,
      "mode": "knowledge",
      "questions": [
        {"id": str, "question": str, "kind": str, "split": "dev" | "test",
         "expected_pages": ["<vault id>:<path>", ...],
         "expected_exchanges": ["<path> L<first>-L<last>", ...],
         "mode": "evidence"}
      ]
    }

- `layer` is the evaluation layer. Layer 1 questions come from a real Vault, so the tool keeps their file
  and its results outside the repository.
- `kind` is one of `title` (제목 그대로), `paraphrase` (의역), `decision` (결정), `how` (방법), `session` (세션),
  `no_answer` (답 없음).
- `split` is `dev` (tuning) or `test` (adoption only).
- `expected_pages` uses the page rule of `measure_memory_recall`: `<vault>:<Vault-relative path>`, where
  `<vault>` is the Graph Home Vault id. `expected_exchanges` uses the exchange rule of
  `measure_session_recall`: the location vg shows for an exchange. Either list may be empty or missing,
  and only `no_answer` may have no expected item at all; such a question is counted but not scored.
- `mode` is the search mode. The set's `mode` is the default (`knowledge` when absent) and a question's
  `mode` overrides it, so session questions can search raw evidence.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from tests.benchmarks.measure_memory_recall import PageRef, parse_page_ref
from tests.benchmarks.measure_session_recall import ExchangeLocation, parse_location
from vault_graph.retrieval.search.search_response import SearchMode

DATASET_FORMAT = "vg-search-eval/1"
LAYERS = (1, 2)
KINDS = ("title", "paraphrase", "decision", "how", "session", "no_answer")
NO_ANSWER_KIND = "no_answer"
SPLITS = ("dev", "test")
SEARCH_MODES: tuple[SearchMode, ...] = ("knowledge", "evidence", "operating", "audit", "all")
DEFAULT_MODE: SearchMode = "knowledge"


@dataclass(frozen=True)
class EvalQuestion:
    question_id: str
    text: str
    kind: str
    split: str
    pages: tuple[PageRef, ...]
    exchanges: tuple[ExchangeLocation, ...]
    mode: SearchMode

    @property
    def scored(self) -> bool:
        return bool(self.pages or self.exchanges)


@dataclass(frozen=True)
class EvalDataset:
    layer: int
    questions: tuple[EvalQuestion, ...]

    def select(self, split: str | None) -> tuple[EvalQuestion, ...]:
        """Questions of one split, or all of them when ``split`` is None."""
        if split is None:
            return self.questions
        if split not in SPLITS:
            raise ValueError(f"split must be one of {', '.join(SPLITS)}")
        return tuple(question for question in self.questions if question.split == split)


def load_dataset(path: Path) -> EvalDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != DATASET_FORMAT:
        raise ValueError(f"question set must be a JSON object with format {DATASET_FORMAT!r}")
    layer = payload.get("layer")
    if layer not in LAYERS or isinstance(layer, bool):
        raise ValueError(f"layer must be one of {', '.join(str(item) for item in LAYERS)}")
    default_mode = _mode(payload.get("mode", DEFAULT_MODE), "question set")
    rows = payload.get("questions")
    if not isinstance(rows, list):
        raise ValueError("questions must be a list")
    questions: list[EvalQuestion] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, start=1):
        question = _question(row, number=number, default_mode=default_mode)
        if question.question_id in seen:
            raise ValueError(f"question {number}: duplicate id {question.question_id!r}")
        seen.add(question.question_id)
        questions.append(question)
    return EvalDataset(layer=int(layer), questions=tuple(questions))


def _question(row: object, *, number: int, default_mode: SearchMode) -> EvalQuestion:
    label = f"question {number}"
    if not isinstance(row, dict):
        raise ValueError(f"{label}: a question must be a JSON object")
    question_id, text, kind, split = row.get("id"), row.get("question"), row.get("kind"), row.get("split")
    if not isinstance(question_id, str) or not question_id or not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label}: id and question must be non-empty strings")
    if kind not in KINDS:
        raise ValueError(f"{label}: kind must be one of {', '.join(KINDS)}")
    if split not in SPLITS:
        raise ValueError(f"{label}: split must be one of {', '.join(SPLITS)}")
    pages = tuple(parse_page_ref(item) for item in _strings(row.get("expected_pages", []), label, "expected_pages"))
    exchanges = tuple(
        parse_location(item) for item in _strings(row.get("expected_exchanges", []), label, "expected_exchanges")
    )
    if not pages and not exchanges and kind != NO_ANSWER_KIND:
        raise ValueError(f"{label}: only {NO_ANSWER_KIND} may have no expected page or exchange")
    mode = _mode(row.get("mode", default_mode), label)
    return EvalQuestion(question_id, text, str(kind), str(split), pages, exchanges, mode)


def _strings(value: object, label: str, field: str) -> Sequence[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label}: {field} must be a list of strings")
    return cast(list[str], value)


def _mode(value: object, label: str) -> SearchMode:
    for mode in SEARCH_MODES:
        if value == mode:
            return mode
    raise ValueError(f"{label}: mode must be one of {', '.join(SEARCH_MODES)}")
