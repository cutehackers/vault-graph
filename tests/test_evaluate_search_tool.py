"""The search evaluation tool (spec 2026-11-11 §4.1.2, A-3)."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.benchmarks import eval_dataset as dataset_tool
from tests.benchmarks import eval_scoring as scoring
from tests.benchmarks import evaluate_search as tool
from tests.benchmarks import measure_session_recall as session_tool
from tests.benchmarks.measure_memory_recall import PageRef
from tests.benchmarks.measure_session_recall import ExchangeLocation
from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings, _deterministic_text_embeddings
from tests.test_vector_indexer import SPEC
from vault_graph.interface.cli.main import app
from vault_graph.retrieval.search.search_response import (
    DocumentRankTrace,
    FusedRankTrace,
    SearchStageTrace,
    SignalRankTrace,
)

FIXTURE_SESSIONS = Path(__file__).parent / "fixtures" / "session_v2" / "raw" / "sessions"
PARSER_SESSION = "raw/sessions/claude-code/2026-11-04-44444444-4444-4444-8444-444444444444-part1.md"


def _question(**fields: object) -> dict[str, object]:
    return {
        "id": "q1",
        "question": "how do we pick the store",
        "kind": "decision",
        "split": "dev",
        "expected_pages": ["main:wiki/a.md"],
        **fields,
    }


def _write_set(path: Path, questions: Sequence[dict[str, object]], **fields: object) -> Path:
    payload = {"format": dataset_tool.DATASET_FORMAT, "layer": 2, "questions": list(questions), **fields}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _score(
    question_id: str,
    kind: str,
    final_rank: int | None,
    *,
    in_candidates: bool = True,
    seconds: float = 0.1,
    scored: bool = True,
    error: str | None = None,
) -> scoring.QuestionScore:
    ranks = scoring.StageRanks(3 if in_candidates else None, None, None, 4 if in_candidates else None, final_rank)
    return scoring.QuestionScore(question_id, kind, "dev", scored, final_rank, ranks, seconds, error)


# Question set -----------------------------------------------------------------------------------


def test_question_set_reads_kind_split_both_answer_rules_and_mode(tmp_path: Path) -> None:
    path = _write_set(
        tmp_path / "q.json",
        [
            _question(),
            _question(
                id="q2",
                kind="session",
                split="test",
                expected_pages=[],
                expected_exchanges=["raw/sessions/s.md L3-L9"],
                mode="evidence",
            ),
            _question(id="q3", kind="no_answer", expected_pages=[]),
        ],
    )

    dataset = dataset_tool.load_dataset(path)

    assert dataset.layer == 2
    first, second, third = dataset.questions
    assert first.pages == (PageRef("main", "wiki/a.md"),) and first.mode == "knowledge" and first.scored
    assert second.exchanges == (ExchangeLocation("raw/sessions/s.md", 3, 9),)
    assert (second.split, second.mode) == ("test", "evidence")
    assert not third.scored
    assert [question.question_id for question in dataset.select("test")] == ["q2"]
    assert len(dataset.select(None)) == 3


@pytest.mark.parametrize(
    ("question", "message"),
    [
        (_question(kind="other"), "kind"),
        (_question(split="train"), "split"),
        (_question(expected_pages=[]), "only no_answer"),
        (_question(expected_pages=["no-vault-prefix"]), "<vault>:<path>"),
        (_question(expected_exchanges=["a.md#L1-L2"]), "L<a>-L<b>"),
        (_question(mode="fast"), "mode"),
    ],
)
def test_question_set_rejects_bad_questions(tmp_path: Path, question: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dataset_tool.load_dataset(_write_set(tmp_path / "q.json", [question]))


def test_question_set_needs_format_layer_and_unique_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        dataset_tool.load_dataset(_write_set(tmp_path / "q.json", [_question(), _question()]))
    with pytest.raises(ValueError, match="layer"):
        dataset_tool.load_dataset(_write_set(tmp_path / "q.json", [_question()], layer=3))
    with pytest.raises(ValueError, match="format"):
        dataset_tool.load_dataset(_write_set(tmp_path / "q.json", [_question()], format="other"))


# Scoring ----------------------------------------------------------------------------------------


EXPECTED_PAGE = scoring.Expected(pages=frozenset({("main", "wiki/a.md")}), exchanges=())
EXPECTED_EXCHANGE = scoring.Expected(pages=frozenset(), exchanges=(ExchangeLocation("s.md", 20, 30),))


def test_matching_uses_the_page_rule_and_the_exchange_overlap_rule() -> None:
    assert EXPECTED_PAGE.matches(scoring.Target(pages=(("main", "wiki/a.md"),), spans=()))
    assert not EXPECTED_PAGE.matches(scoring.Target(pages=(("other", "wiki/a.md"),), spans=()))
    assert EXPECTED_EXCHANGE.matches(scoring.Target(pages=(), spans=(("s.md", 28, 40),)))
    assert not EXPECTED_EXCHANGE.matches(scoring.Target(pages=(), spans=(("s.md", 31, 40),)))
    targets = [
        scoring.Target(pages=(), spans=(("other.md", 20, 30),)),
        scoring.Target(pages=(), spans=(("s.md", 1, 10),)),
        scoring.Target(pages=(), spans=(("s.md", 25, 26),)),
    ]
    units = [session_tool.ResultUnit(target.spans, False) for target in targets]
    assert scoring.first_rank(EXPECTED_EXCHANGE, targets) == session_tool.first_rank(EXPECTED_EXCHANGE.exchanges, units)


def _trace() -> SearchStageTrace:
    return SearchStageTrace(
        signal_ranks=(
            SignalRankTrace("keyword", "main", "main:wiki/b.md", "b1", 1, 2.0),
            SignalRankTrace("keyword", "main", "main:wiki/a.md", "a2", 2, 1.0),
            SignalRankTrace("vector", "main", "main:wiki/a.md", "a1", 3, 0.5),
            SignalRankTrace("graph", "main", "main:wiki/b.md", "b1", 1, 0.9),
        ),
        fused_ranks=(
            FusedRankTrace("main", "main:wiki/b.md", "b1", 1, 0.3),
            FusedRankTrace("main", "main:wiki/a.md", "a2", 2, 0.2),
            FusedRankTrace("main", "main:wiki/a.md", "a1", 3, 0.1),
        ),
        document_ranks=(
            DocumentRankTrace(1, "r-b", "main", "main:wiki/b.md", "wiki/b.md", ()),
            DocumentRankTrace(2, "r-a", "main", "main:wiki/a.md", "wiki/a.md", ()),
        ),
        candidate_limit=40,
        refilled=False,
    )


def _chunk_target(vault_id: str, chunk_id: str) -> scoring.Target | None:
    paths = {"a1": "wiki/a.md", "a2": "wiki/a.md", "b1": "wiki/b.md"}
    path = paths.get(chunk_id)
    return None if path is None else scoring.Target(pages=((vault_id, path),), spans=())


def test_stage_ranks_are_the_best_rank_of_a_matching_chunk_per_stage() -> None:
    ranks = scoring.stage_ranks(EXPECTED_PAGE, _trace(), chunk_target=_chunk_target, final_rank=2)

    assert ranks == scoring.StageRanks(keyword=2, vector=3, graph=None, fused=2, document=2)
    assert ranks.in_candidates


def test_stage_ranks_are_empty_when_no_signal_holds_the_answer() -> None:
    expected = scoring.Expected(pages=frozenset({("main", "wiki/z.md")}), exchanges=())

    ranks = scoring.stage_ranks(expected, _trace(), chunk_target=_chunk_target, final_rank=None)

    assert ranks == scoring.StageRanks(None, None, None, None, None)
    assert not ranks.in_candidates


def test_outcome_is_hit_rank_loss_or_candidate_loss() -> None:
    assert _score("q", "title", 5).outcome == "hit"
    assert _score("q", "title", 6).outcome == "rank_loss"
    assert _score("q", "title", None).outcome == "rank_loss"
    assert _score("q", "title", None, in_candidates=False).outcome == "candidate_loss"
    assert _score("q", "no_answer", None, scored=False).outcome is None
    assert _score("q", "title", None, error="boom").outcome is None


def test_summary_keeps_the_session_tool_formulas_and_adds_kinds_losses_and_time() -> None:
    scores = [
        _score("q1", "title", 1, seconds=0.1),
        _score("q2", "title", 7, seconds=0.2),
        _score("q3", "paraphrase", None, in_candidates=False, seconds=0.3),
        _score("q4", "paraphrase", 3, seconds=0.4),
        _score("q5", "no_answer", None, scored=False, seconds=0.5),
        _score("q6", "how", None, error="search failed", seconds=9.0),
    ]
    session_scores = [
        session_tool.QuestionScore(s.question_id, "file", s.final_rank, 0, 0, s.seconds, None)
        for s in scores
        if s.scored and s.error is None
    ]

    summary = scoring.summarize(scores)
    session_summary = session_tool.summarize(session_scores, stage="c", commit="x")

    for key in ("recall_at_5", "recall_at_10", "mrr"):
        assert summary[key] == session_summary[key]
    assert (summary["questions"], summary["scored"], summary["failed"]) == (6, 4, 1)
    assert summary["outcomes"] == {"hit": 2, "rank_loss": 1, "candidate_loss": 1}
    by_kind = summary["by_kind"]
    assert isinstance(by_kind, dict)
    assert by_kind["title"] == {
        "questions": 2,
        "failed": 0,
        "scored": 2,
        "recall_at_5": 0.5,
        "recall_at_10": 1.0,
        "mrr": round((1 + 1 / 7) / 2, 4),
        "outcomes": {"hit": 1, "rank_loss": 1, "candidate_loss": 0},
    }
    assert by_kind["no_answer"]["scored"] == 0 and by_kind["no_answer"]["recall_at_5"] is None
    assert summary["seconds"] == {"p50": 0.3, "p95": 0.5}


def test_percentile_is_nearest_rank() -> None:
    values = [float(value) for value in range(1, 21)]
    assert scoring.percentile(values, 0.5) == 10.0
    assert scoring.percentile(values, 0.95) == 19.0
    assert scoring.percentile([4.0], 0.95) == 4.0
    assert scoring.percentile([], 0.5) is None


# Boundaries ------------------------------------------------------------------------------------


def test_layer1_question_file_and_results_must_be_outside_the_repository(tmp_path: Path) -> None:
    inside = tool.REPO_ROOT / "tests" / "fixtures"
    home = tmp_path / "home"
    with pytest.raises(ValueError, match="outside"):
        tool.check_paths(layer=1, questions=inside / "q.json", out_dir=tmp_path / "out", graph_home=home)
    with pytest.raises(ValueError, match="outside"):
        tool.check_paths(layer=1, questions=tmp_path / "q.json", out_dir=inside / "out", graph_home=home)
    tool.check_paths(layer=2, questions=inside / "q.json", out_dir=tmp_path / "out", graph_home=home)


def test_layer1_run_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    questions = _write_set(tmp_path / "q.json", [_question()], layer=1)
    out = tool.REPO_ROOT / "tests" / "eval-out-must-not-exist"

    with pytest.raises(ValueError, match="outside"):
        tool.main(questions, graph_home=tmp_path / "home", out_dir=out, open_ports=_no_ports)

    assert not out.exists()


def test_the_default_graph_home_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool, "DEFAULT_GRAPH_HOME", tmp_path / "real-home")
    questions = _write_set(tmp_path / "q.json", [_question()])

    with pytest.raises(ValueError, match="copy"):
        tool.main(questions, graph_home=tmp_path / "real-home", out_dir=tmp_path / "out", open_ports=_no_ports)


def _no_ports(graph_home: Path, include_graph: bool) -> tool.SearchPorts:
    raise AssertionError("the run must stop before it opens the Graph Home")


# One process run on a synthetic mini Vault ------------------------------------------------------


def _files(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _mini_graph_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_SESSIONS, vault / "raw" / "sessions")
    pages = {
        "wiki/decisions/use-sqlite.md": "# Use SQLite for metadata\n\nWe keep the metadata store in SQLite.\n",
        "wiki/how/rebuild-index.md": "# Rebuild the index\n\nRun vg index after a Vault moves.\n",
        "wiki/notes/kiwi.md": "# Kiwi tokenizer\n\nKorean morphemes for keyword search.\n",
    }
    for path, body in pages.items():
        (vault / path).parent.mkdir(parents=True, exist_ok=True)
        (vault / path).write_text(body, encoding="utf-8")
    home = tmp_path / "home"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(home)]).exit_code == 0
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    assert runner.invoke(app, ["index", "--graph-home", str(home)]).exit_code == 0
    monkeypatch.setattr(
        "vault_graph.interface.composition.adapters.text_embeddings.text_embeddings_for",
        lambda *_args, **_kwargs: _ConfiguredDeterministicTextEmbeddings(SPEC),
    )
    lines = (vault / PARSER_SESSION).read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines, start=1) if "· u-401" in line)
    return home, f"{PARSER_SESSION} L{start}-L{len(lines)}"


def test_one_run_scores_every_kind_in_one_process_and_leaves_the_graph_home_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, exchange = _mini_graph_home(tmp_path, monkeypatch)
    ports = tool.open_search_ports(home, False)
    vault_id = ports.catalog.active_vault_id
    questions = _write_set(
        tmp_path / "q.json",
        [
            _question(
                id="t1",
                kind="title",
                question="Use SQLite for metadata",
                expected_pages=[f"{vault_id}:wiki/decisions/use-sqlite.md"],
            ),
            _question(
                id="h1",
                kind="how",
                split="test",
                question="Rebuild the index",
                expected_pages=[f"{vault_id}:wiki/how/rebuild-index.md"],
            ),
            _question(
                id="s1",
                kind="session",
                question="-- parser drop last token quoted string",
                expected_pages=[],
                expected_exchanges=[exchange],
                mode="evidence",
            ),
            _question(id="n1", kind="no_answer", question="zebra migration plan", expected_pages=[]),
            _question(
                id="x1", kind="paraphrase", question="the page nobody wrote", expected_pages=["nowhere:wiki/x.md"]
            ),
        ],
    )
    before = _files(home)
    out = tmp_path / "out"

    summary = tool.main(questions, graph_home=home, out_dir=out)

    rows = [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    by_id = {row["id"]: row for row in rows}
    assert by_id["t1"]["outcome"] == "hit" and by_id["t1"]["final_rank"] == 1
    assert by_id["t1"]["keyword_rank"] is not None and by_id["t1"]["fused_rank"] is not None
    assert by_id["h1"]["split"] == "test" and by_id["h1"]["outcome"] == "hit"
    assert by_id["s1"]["outcome"] == "hit", by_id["s1"]
    assert by_id["n1"]["outcome"] is None and by_id["n1"]["error"] is None
    assert "unknown Vault" in by_id["x1"]["error"]
    assert summary["questions"] == 5 and summary["failed"] == 1 and summary["scored"] == 3
    assert summary["recall_at_5"] == 1.0
    by_kind = summary["by_kind"]
    assert isinstance(by_kind, dict) and set(by_kind) == {"title", "paraphrase", "how", "session", "no_answer"}
    seconds = summary["seconds"]
    assert isinstance(seconds, dict) and seconds["p50"] is not None and seconds["p95"] >= seconds["p50"]
    written = (out / "results.jsonl").read_text(encoding="utf-8") + (out / "summary.json").read_text(encoding="utf-8")
    assert "SQLite" not in written and "quoted" not in written
    assert _files(home) == before
    assert not (home / "usage").exists()
    table = tool.format_table(summary)
    assert "candidate_loss" in table and "p95" in table and "SQLite" not in table


def test_split_option_runs_only_that_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, _ = _mini_graph_home(tmp_path, monkeypatch)
    vault_id = tool.open_search_ports(home, False).catalog.active_vault_id
    questions = _write_set(
        tmp_path / "q.json",
        [
            _question(
                id="d1", kind="title", question="Kiwi tokenizer", expected_pages=[f"{vault_id}:wiki/notes/kiwi.md"]
            ),
            _question(
                id="t1",
                kind="title",
                split="test",
                question="Use SQLite",
                expected_pages=[f"{vault_id}:wiki/decisions/use-sqlite.md"],
            ),
        ],
    )

    summary = tool.main(questions, graph_home=home, out_dir=tmp_path / "out", split="dev")

    assert summary["questions"] == 1 and summary["split"] == "dev"
