"""Spec 2026-11-05 §4.3.1 단기 수정 and A-13: vector retry interval and the session-start warning."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_hook_session_start import (  # noqa: F401 - pytest fixtures used by name
    base,
    catch_up,
    fake_embeddings,
    fixture_files_stay_unchanged,
    graph_home,
    hook,
)
from tests.test_cli_vector_indexing import _deterministic_text_embeddings, write_page
from vault_graph.errors import VectorStoreError
from vault_graph.indexing.vector_failure_log import (
    VECTOR_FAILURE_LOG,
    clear_vector_failure,
    failure_warning,
    read_vector_failures,
    record_vector_failure,
    vector_retry_pending,
)
from vault_graph.interface.cli import hook_commands
from vault_graph.interface.cli.main import app

runner = CliRunner()
T0 = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
SQL_ERROR = "Error executing plan: Internal error: too many SQL variables"


def test_same_error_doubles_the_interval_up_to_24_hours(tmp_path: Path) -> None:
    expected_hours = [1, 2, 4, 8, 16, 24, 24]
    for count, hours in enumerate(expected_hours, start=1):
        now = T0 + timedelta(days=count)
        failure = record_vector_failure(tmp_path, "main", SQL_ERROR, now=now)
        assert failure.count == count
        assert failure.first_failed_at == T0 + timedelta(days=1)
        assert vector_retry_pending(tmp_path, "main", now=now + timedelta(hours=hours) - timedelta(minutes=1))
        assert not vector_retry_pending(tmp_path, "main", now=now + timedelta(hours=hours))


def test_two_failures_skip_vectors_for_two_hours_only(tmp_path: Path) -> None:
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0 + timedelta(minutes=5))
    assert vector_retry_pending(tmp_path, "main", now=T0 + timedelta(hours=2))
    assert not vector_retry_pending(tmp_path, "main", now=T0 + timedelta(hours=2, minutes=5))
    assert not vector_retry_pending(tmp_path, "other", now=T0 + timedelta(minutes=10))


def test_a_different_error_starts_counting_again(tmp_path: Path) -> None:
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)
    failure = record_vector_failure(tmp_path, "main", "model unavailable", now=T0 + timedelta(hours=3))
    assert failure.count == 1
    assert failure.first_failed_at == T0 + timedelta(hours=3)
    assert failure.error_head == "model unavailable"


def test_numbers_in_the_error_do_not_change_its_digest(tmp_path: Path) -> None:
    record_vector_failure(tmp_path, "main", "collection has 33065 rows", now=T0)
    assert record_vector_failure(tmp_path, "main", "collection has 33071 rows", now=T0).count == 2


def test_clear_removes_only_that_vault(tmp_path: Path) -> None:
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)
    record_vector_failure(tmp_path, "other", SQL_ERROR, now=T0)
    clear_vector_failure(tmp_path, "main")
    assert set(read_vector_failures(tmp_path)) == {"other"}


def test_a_broken_log_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / VECTOR_FAILURE_LOG
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_vector_failures(tmp_path) == {}
    assert not vector_retry_pending(tmp_path, "main", now=T0)
    assert record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0).count == 1


def test_warning_names_the_vault_hours_and_error_head(tmp_path: Path) -> None:
    record_vector_failure(tmp_path, "main", SQL_ERROR + "\nTraceback line", now=T0)
    failure = record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0 + timedelta(hours=1))
    assert failure_warning(failure, now=T0 + timedelta(hours=5, minutes=30)) == (
        f"벡터 색인이 main에서 5시간째 실패 중: {SQL_ERROR}"
    )


def _raise_manifest_error(**_: object) -> tuple[object, ...]:
    raise VectorStoreError(SQL_ERROR)


def test_vg_index_records_a_vector_failure_and_clears_it_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    home = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(home), "--vault-id", "main"])
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    with monkeypatch.context() as patch:
        patch.setattr("vault_graph.indexing.vector_index_adapter._manifest_for_scopes", _raise_manifest_error)
        assert runner.invoke(app, ["index", "--graph-home", str(home)]).exit_code == 1
    failures = read_vector_failures(home)
    assert set(failures) == {"main"}
    assert failures["main"].count == 1
    assert failures["main"].error_head == SQL_ERROR

    assert runner.invoke(app, ["index", "--graph-home", str(home)]).exit_code == 0
    assert read_vector_failures(home) == {}


def test_vg_index_no_vector_indexes_metadata_and_keeps_the_failure_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    home = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(home), "--vault-id", "main"])
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    assert runner.invoke(app, ["index", "--graph-home", str(home)]).exit_code == 0
    record_vector_failure(home, "main", SQL_ERROR, now=datetime.now(UTC))

    write_page(vault_root, "wiki/page.md", "# Page\nChanged\n")
    result = runner.invoke(app, ["index", "--graph-home", str(home), "--no-vector"])

    assert result.exit_code == 0, result.output
    assert "changed: 1" in result.stdout
    assert "vector_mode" not in result.stdout
    assert set(read_vector_failures(home)) == {"main"}


def test_catch_up_skips_vectors_only_while_the_retry_interval_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "vault_graph.interface.cli.hook_commands.subprocess.run", lambda args, **_: calls.append(list(args))
    )
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=T0)

    hook_commands._run_vg_index(str(tmp_path), "main", now=T0 + timedelta(hours=1))
    hook_commands._run_vg_index(str(tmp_path), "other", now=T0 + timedelta(hours=1))
    hook_commands._run_vg_index(str(tmp_path), "main", now=T0 + timedelta(hours=2))

    assert [call[-1] for call in calls] == ["--no-vector", "other", "main"]
    assert calls[0][-3:-1] == ["--vault-id", "main"]


def test_vector_check_is_skipped_while_the_retry_interval_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    indexed: list[str] = []
    monkeypatch.setattr(hook_commands, "_wait_for_gate", lambda *_, **__: True)

    def vectors_need_catch_up(_: object, vault_id: str) -> bool:
        checked.append(vault_id)
        return True

    monkeypatch.setattr(hook_commands, "vectors_need_catch_up", vectors_need_catch_up)
    monkeypatch.setattr(hook_commands, "_run_vg_index", lambda _, vault_id, **__: indexed.append(vault_id))
    record_vector_failure(tmp_path, "main", SQL_ERROR, now=datetime.now(UTC))
    plan = json.dumps({"index": [], "check": ["main", "other"]})
    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.sys.argv", ["-c", str(tmp_path), "0", plan])

    hook_commands.run_catch_up_index()

    assert checked == ["other"]
    assert indexed == ["other"]


def test_session_start_warns_on_stderr_and_adds_one_stdout_line(base: Path, graph_home: Path) -> None:  # noqa: F811
    before = hook(graph_home, base)
    record_vector_failure(graph_home, "main", SQL_ERROR, now=datetime.now(UTC) - timedelta(hours=3))

    after = hook(graph_home, base)

    assert after.exit_code == 0, after.output
    added = [line for line in after.stdout.splitlines() if line not in before.stdout.splitlines()]
    assert added == [f"- 벡터 색인이 main에서 3시간째 실패 중: {SQL_ERROR}"]
    warnings = [line for line in after.stderr.splitlines() if "벡터 색인이" in line]
    assert warnings == [f"vg hook session-start: warning: 벡터 색인이 main에서 3시간째 실패 중: {SQL_ERROR}"]


def test_vg_index_no_vector_reports_a_failed_vector_drop_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vault_graph.indexing.index_service import IndexService
    from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    home = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(home), "--vault-id", "main"])
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    assert runner.invoke(app, ["index", "--graph-home", str(home)]).exit_code == 0
    first = ProjectionGenerationManager(home).active_layout()

    def fail(self: IndexService, removed: set[tuple[str, str]]) -> None:
        raise VectorStoreError("store locked")

    monkeypatch.setattr(IndexService, "_drop_removed_chunk_vectors", fail)
    write_page(vault_root, "wiki/page.md", "# Page\nChanged\n")
    result = runner.invoke(app, ["index", "--graph-home", str(home), "--no-vector"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "vector_failed: True" in result.stdout
    assert "store locked" in result.stdout
    assert ProjectionGenerationManager(home).active_layout() == first
