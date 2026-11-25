"""`vg hook capture` queues one fact job and starts the fact worker without waiting (spec 2026-11-16 A12, A13, A17).

The fake Vault hook launcher prints a fixed `sessions capture --json` result. The worker the hook starts is a slow
fake: `fact_worker._WORKER_SCRIPT` is replaced by a script that records its arguments and sleeps, so no test
reaches a real extractor and the timing test shows the hook does not wait for extraction.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli import hook_commands
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters import fact_worker
from vault_graph.interface.composition.adapters.fact_queue import list_fact_jobs, read_fact_job
from vault_graph.interface.composition.adapters.fact_worker import FACTS_WORKER_LOCK
from vault_graph.operation.scope.facts_settings import FactsSettings, facts_settings_path, save_facts_settings

runner = CliRunner()

PART = "raw/sessions/2026-11-16-s1-part1.md"

FAKE_LAUNCHER = f"""\
import json, os, sys
data = sys.stdin.buffer.read()
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")
mode = os.environ.get("FAKE_LAUNCHER_MODE", "written")
sys.stderr.write("launcher note\\n")
print(json.dumps({{
    "status": mode,
    "message": "fake",
    "vault": None if mode == "skipped" else "proj-vault",
    "path": "{PART}" if mode == "written" else None,
}}))
"""

# Records how it was started, then sleeps like an extractor that takes a long time.
SLOW_WORKER = (
    "import os, sys, time; open(os.environ['FAKE_WORKER_MARK'], 'w').write(' '.join(sys.argv[1:])); time.sleep(3)"
)

HOOK_JSON = (
    b'{"session_id": "s1", "transcript_path": "/nonexistent/t.jsonl", "cwd": "/tmp", "hook_event_name": "SessionEnd"}'
)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config = tmp_path / "claude" / "vault-builder"
    config.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    (vault / "raw" / "sessions").mkdir(parents=True)
    (vault / "wiki").mkdir()
    (vault / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    # A session captured before the upgrade. It must never be queued.
    (vault / "raw" / "sessions" / "2026-11-01-old-part1.md").write_text("old\n", encoding="utf-8")
    vault_map = config / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"proj-vault": {"path": str(vault), "role": "personal"}}, "projects": {}}),
        encoding="utf-8",
    )
    (config / "vault_hooks.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(tmp_path / "launcher.log"))
    monkeypatch.setenv("FAKE_WORKER_MARK", str(tmp_path / "worker.mark"))
    for name in ("FAKE_LAUNCHER_MODE", "VAULT_GRAPH_FACTS_CHILD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(fact_worker, "_WORKER_SCRIPT", SLOW_WORKER)
    graph_home = home / ".vault-graph"
    init = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert init.exit_code == 0, init.output
    return {
        "map": vault_map,
        "vault": vault,
        "graph_home": graph_home,
        "launcher_log": tmp_path / "launcher.log",
        "mark": tmp_path / "worker.mark",
    }


def capture(world: dict[str, Path]) -> Result:
    return runner.invoke(app, ["hook", "capture", "--vault-map", str(world["map"])], input=HOOK_JSON)


def turn_off(graph_home: Path) -> None:
    save_facts_settings(
        facts_settings_path(graph_home),
        FactsSettings(enabled=False, extractor="claude", endpoint=None, model="claude-sonnet-5-5"),
    )


def wait_for(path: Path, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8"):
            return True
        time.sleep(0.02)
    return False


def notice_lines(result: Result) -> list[str]:
    return [line for line in result.stderr.splitlines() if "vg facts off" in line]


def test_written_capture_queues_one_job_and_starts_the_worker(world: dict[str, Path]) -> None:
    result = capture(world)

    assert result.exit_code == 0, result.output
    jobs = list_fact_jobs(world["graph_home"])
    assert len(jobs) == 1
    job = read_fact_job(jobs[0])
    assert (job.vault, job.vault_root, job.part) == ("proj-vault", world["vault"].resolve(), PART)
    assert wait_for(world["mark"])
    started = world["mark"].read_text(encoding="utf-8")
    assert f"facts worker --graph-home {world['graph_home']}" in started


def test_hook_returns_within_one_second_with_a_slow_worker(world: dict[str, Path]) -> None:
    started = time.monotonic()
    result = capture(world)
    elapsed = time.monotonic() - started

    assert result.exit_code == 0, result.output
    assert elapsed < 1.0
    # The slow worker still runs after the hook returned: it holds the worker lock.
    assert wait_for(world["mark"])
    assert not fact_worker.start_fact_worker(world["graph_home"])


def test_exit_code_and_output_match_facts_off(world: dict[str, Path], tmp_path: Path) -> None:
    first_on = capture(world)
    assert wait_for(world["mark"])
    second_on = capture(world)
    turn_off(world["graph_home"])
    off = capture(world)

    assert first_on.exit_code == second_on.exit_code == off.exit_code == 0
    assert first_on.stdout == second_on.stdout == off.stdout
    assert second_on.stderr == off.stderr
    # The first run differs only by the one-time notice line.
    assert [line for line in first_on.stderr.splitlines() if line not in notice_lines(first_on)] == (
        off.stderr.splitlines()
    )


def test_lock_held_starts_no_worker_but_keeps_the_job(world: dict[str, Path]) -> None:
    graph_home = world["graph_home"]
    (graph_home / FACTS_WORKER_LOCK.parent).mkdir(parents=True, exist_ok=True)
    descriptor = os.open(graph_home / FACTS_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = capture(world)
        time.sleep(0.3)
    finally:
        os.close(descriptor)

    assert result.exit_code == 0, result.output
    assert len(list_fact_jobs(graph_home)) == 1
    assert not world["mark"].exists()


@pytest.mark.parametrize("mode", ["no-new-turns", "skipped"])
def test_capture_that_is_not_written_queues_nothing(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", mode)

    result = capture(world)

    assert result.exit_code == 0, result.output
    assert list_fact_jobs(world["graph_home"]) == []
    assert notice_lines(result) == []
    time.sleep(0.2)
    assert not world["mark"].exists()


def test_facts_off_queues_nothing(world: dict[str, Path]) -> None:
    turn_off(world["graph_home"])

    result = capture(world)

    assert result.exit_code == 0, result.output
    assert list_fact_jobs(world["graph_home"]) == []
    assert notice_lines(result) == []


def test_broken_settings_file_reads_as_off(world: dict[str, Path]) -> None:
    path = facts_settings_path(world["graph_home"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    result = capture(world)

    assert result.exit_code == 0, result.output
    assert list_fact_jobs(world["graph_home"]) == []


def test_uninitialized_graph_home_queues_nothing(
    world: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_home = tmp_path / "fresh-home"
    other_home.mkdir()
    monkeypatch.setenv("HOME", str(other_home))

    result = capture(world)

    assert result.exit_code == 0, result.output
    assert not (other_home / ".vault-graph").exists()


def test_first_job_prints_the_notice_once_and_records_it(world: dict[str, Path]) -> None:
    assert not facts_settings_path(world["graph_home"]).exists()

    first = capture(world)
    second = capture(world)

    lines = notice_lines(first)
    assert len(lines) == 1
    assert "on" in lines[0] and "Claude Code" in lines[0]
    assert "local llama-server when it answers" in lines[0]
    assert notice_lines(second) == []
    assert hook_commands.facts_notice_path(world["graph_home"]).is_file()
    # Past sessions are not queued: only the two new captures are.
    parts = [read_fact_job(path).part for path in list_fact_jobs(world["graph_home"])]
    assert parts == [PART, PART]


def test_child_session_capture_does_nothing(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULT_GRAPH_FACTS_CHILD", "1")

    result = capture(world)

    assert result.exit_code == 0
    assert result.stdout == "" and result.stderr == ""
    assert not world["launcher_log"].exists()
    assert list_fact_jobs(world["graph_home"]) == []


def test_child_session_start_does_nothing(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAULT_GRAPH_FACTS_CHILD", "1")

    def refuse(*_args: object, **_kwargs: object) -> object:
        pytest.fail("the child session start must not refresh or recall")

    monkeypatch.setattr(hook_commands, "recall", refuse)
    monkeypatch.setattr(hook_commands, "refresh_linked_vaults", refuse)
    monkeypatch.setattr(hook_commands, "ReadOnlyServiceFactory", refuse)

    result = runner.invoke(
        app,
        ["hook", "session-start", "--graph-home", str(world["graph_home"]), "--vault-map", str(world["map"])],
        input='{"cwd": "/tmp", "source": "startup", "session_id": "s1"}',
    )

    assert result.exit_code == 0
    assert result.stdout == "" and result.stderr == ""
