"""The session recall measurement tool (spec 2026-11-05 §4.2.10, A-8 tool part)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.benchmarks import measure_session_recall as tool
from tests.test_cli_vector_indexing import _deterministic_text_embeddings
from vault_graph.interface.cli.main import app

FIXTURE_SESSIONS = Path(__file__).parent / "fixtures" / "session_v2" / "raw" / "sessions"
PARSER_SESSION = "raw/sessions/claude-code/2026-11-04-44444444-4444-4444-8444-444444444444-part1.md"


def unit(*spans: tuple[str, int, int], subagent: bool = False) -> tool.ResultUnit:
    return tool.ResultUnit(spans=spans, subagent=subagent)


def test_location_format_matches_what_vg_shows() -> None:
    location = tool.parse_location("raw/sessions/a.md L12-L40")
    assert location == tool.ExchangeLocation("raw/sessions/a.md", 12, 40)
    with pytest.raises(ValueError):
        tool.parse_location("raw/sessions/a.md#L12-L40")
    with pytest.raises(ValueError):
        tool.parse_location("raw/sessions/a.md L40-L12")


def test_questions_need_the_four_fields_and_a_known_kind(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text(
        json.dumps({"id": "q1", "question": "why", "expected_exchanges": ["a.md L1-L5"], "kind": "error"}) + "\n",
        encoding="utf-8",
    )
    assert tool.load_questions(path)[0].expected == (tool.ExchangeLocation("a.md", 1, 5),)
    path.write_text(json.dumps({"id": "q1", "question": "why", "expected_exchanges": [], "kind": "x"}) + "\n")
    with pytest.raises(ValueError):
        tool.load_questions(path)


def test_rank_is_the_first_result_overlapping_an_expected_exchange() -> None:
    expected = (tool.ExchangeLocation("s.md", 20, 30),)
    units = (unit(("other.md", 20, 30)), unit(("s.md", 1, 10)), unit(("s.md", 25, 26)), unit(("s.md", 28, 40)))
    assert tool.first_rank(expected, units) == 3
    assert tool.first_rank(expected, (unit(("s.md", 31, 40)),)) is None


def test_summary_counts_recall_mrr_kinds_and_failures_without_question_text() -> None:
    scores = [
        tool.QuestionScore("q1", "file", 1, 1, 10, 0.5, None),
        tool.QuestionScore("q2", "file", 7, 0, 10, 0.7, None),
        tool.QuestionScore("q3", "how", None, 0, 10, 0.6, None),
        tool.QuestionScore("q4", "how", None, 0, 0, 0.1, "vg search exited 1"),
    ]
    summary = tool.summarize(scores, stage="c", commit="abc")
    assert summary["questions"] == 4 and summary["failed"] == 1
    assert summary["recall_at_5"] == round(1 / 3, 4)
    assert summary["recall_at_10"] == round(2 / 3, 4)
    assert summary["mrr"] == round((1 + 1 / 7) / 3, 4)
    assert summary["by_kind"] == {
        "file": {"questions": 2, "recall_at_5": 0.5, "recall_at_10": 1.0},
        "how": {"questions": 1, "recall_at_5": 0.0, "recall_at_10": 0.0},
    }
    assert summary["subagent_share_in_top10"] == round(1 / 30, 4)
    assert "why" not in json.dumps(summary)


def test_question_file_and_output_must_be_outside_the_repository(tmp_path: Path) -> None:
    inside = tool.REPO_ROOT / "tests" / "fixtures"
    with pytest.raises(ValueError, match="outside"):
        tool.main(inside / "q.jsonl", tmp_path, tmp_path / "out", "c")


def test_runs_vg_search_as_a_subprocess_and_writes_totals_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_SESSIONS, vault / "raw" / "sessions")
    home = tmp_path / "home"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(home)]).exit_code == 0
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    # The subprocess has no fake embeddings, so it searches by keyword; metadata is enough here.
    assert runner.invoke(app, ["index", "--graph-home", str(home), "--no-vector"]).exit_code == 0

    lines = (vault / PARSER_SESSION).read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines, start=1) if "· u-401" in line)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "parser",
                "question": "-- parser drop last token quoted string",
                "expected_exchanges": [f"{PARSER_SESSION} L{start}-L{len(lines)}"],
                "kind": "error",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    summary = tool.main(questions, home, out, "c")

    assert summary["failed"] == 0, (out / "results.jsonl").read_text(encoding="utf-8")
    assert summary["recall_at_5"] == 1.0
    assert (out / "results.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert "quoted" not in (out / "summary.json").read_text(encoding="utf-8")
