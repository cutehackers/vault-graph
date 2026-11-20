"""`vg hook capture` starts the dream worker without waiting, and only when dreaming is on (spec 2026-11-19 D2).

The fake Vault hook launcher prints a fixed `sessions capture --json` result. The worker the hook starts is a slow
fake: `dream_worker._WORKER_SCRIPT` is replaced by a script that records its arguments and sleeps, so no test
reaches a real judge and the timing test shows the hook does not wait for a dream run.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters import dream_worker
from vault_graph.interface.composition.adapters.dream_worker import DREAM_WORKER_LOCK, DreamProposal, DreamRun
from vault_graph.operation.scope.dream_settings import DreamSettings, dream_settings_path, save_dream_settings
from vault_graph.operation.scope.facts_settings import FactsSettings, facts_settings_path, save_facts_settings

runner = CliRunner()

FAKE_LAUNCHER = """\
import json, os, sys
sys.stdin.buffer.read()
mode = os.environ.get("FAKE_LAUNCHER_MODE", "written")
print(json.dumps({
    "status": mode,
    "message": "fake",
    "vault": None if mode == "skipped" else "proj-vault",
    "path": "raw/sessions/2026-11-19-s1-part1.md" if mode == "written" else None,
}))
"""

# Records how it was started, then sleeps like a judge that takes a long time.
SLOW_WORKER = (
    "import os, sys, time; open(os.environ['FAKE_WORKER_MARK'], 'w').write(' '.join(sys.argv[1:])); time.sleep(3)"
)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config = tmp_path / "claude" / "vault-builder"
    config.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    (vault / "raw" / "sessions").mkdir(parents=True)
    (vault / "wiki").mkdir()
    (vault / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    vault_map = config / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"proj-vault": {"path": str(vault), "role": "personal"}}, "projects": {}}),
        encoding="utf-8",
    )
    (config / "vault_hooks.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FAKE_WORKER_MARK", str(tmp_path / "worker.mark"))
    for name in ("FAKE_LAUNCHER_MODE", "VAULT_GRAPH_FACTS_CHILD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dream_worker, "_WORKER_SCRIPT", SLOW_WORKER)
    graph_home = home / ".vault-graph"
    init = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert init.exit_code == 0, init.output
    # Fact extraction is on by default and would start its own worker. These tests are about dreaming only.
    save_facts_settings(
        facts_settings_path(graph_home),
        FactsSettings(enabled=False, extractor="claude", endpoint=None, model="claude-sonnet-5-5"),
    )
    return {"map": vault_map, "graph_home": graph_home, "project": project, "mark": tmp_path / "worker.mark"}


def capture(world: dict[str, Path], *, cwd: str | None = None) -> Result:
    hook_json = json.dumps(
        {
            "session_id": "s1",
            "transcript_path": "/nonexistent/t.jsonl",
            "cwd": cwd if cwd is not None else str(world["project"]),
            "hook_event_name": "SessionEnd",
        }
    )
    return runner.invoke(app, ["hook", "capture", "--vault-map", str(world["map"])], input=hook_json)


def turn_on(graph_home: Path) -> None:
    save_dream_settings(dream_settings_path(graph_home), DreamSettings(enabled=True))


def wait_for(path: Path, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8"):
            return True
        time.sleep(0.02)
    return False


def test_dreaming_is_off_by_default_so_capture_starts_no_worker(world: dict[str, Path]) -> None:
    result = capture(world)

    assert result.exit_code == 0, result.output
    assert not wait_for(world["mark"], timeout_s=0.5)
    assert not (world["graph_home"] / DREAM_WORKER_LOCK).exists()


def test_a_written_capture_starts_the_worker_for_the_hook_cwd(world: dict[str, Path]) -> None:
    turn_on(world["graph_home"])

    result = capture(world)

    assert result.exit_code == 0, result.output
    assert wait_for(world["mark"])
    started = world["mark"].read_text(encoding="utf-8")
    assert f"dream worker --graph-home {world['graph_home']} --cwd {world['project']} --lock-fd " in started
    assert started.endswith(f"--vault-map {world['map']}")


def test_the_hook_does_not_wait_for_the_dream_run(world: dict[str, Path]) -> None:
    turn_on(world["graph_home"])

    started = time.monotonic()
    result = capture(world)
    elapsed = time.monotonic() - started

    assert result.exit_code == 0, result.output
    assert elapsed < 2.0  # the fake worker sleeps 3 seconds
    assert wait_for(world["mark"])


@pytest.mark.parametrize("mode", ["no-new-turns", "skipped"])
def test_a_capture_that_wrote_nothing_starts_no_worker(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    turn_on(world["graph_home"])
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", mode)

    assert capture(world).exit_code == 0
    assert not wait_for(world["mark"], timeout_s=0.5)


def test_a_running_worker_keeps_the_lock_so_no_second_one_starts(world: dict[str, Path]) -> None:
    turn_on(world["graph_home"])
    lock = world["graph_home"] / DREAM_WORKER_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert capture(world).exit_code == 0
        assert not wait_for(world["mark"], timeout_s=0.5)
    finally:
        os.close(descriptor)


def test_the_child_session_of_a_judge_neither_captures_nor_dreams(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    turn_on(world["graph_home"])
    monkeypatch.setenv("VAULT_GRAPH_FACTS_CHILD", "1")

    result = capture(world)

    assert result.exit_code == 0
    assert result.output == ""
    assert not wait_for(world["mark"], timeout_s=0.5)


def test_a_broken_settings_file_or_a_hook_without_cwd_starts_nothing(world: dict[str, Path]) -> None:
    turn_on(world["graph_home"])
    assert capture(world, cwd="").exit_code == 0
    assert not wait_for(world["mark"], timeout_s=0.5)

    dream_settings_path(world["graph_home"]).write_text("{broken", encoding="utf-8")
    assert capture(world).exit_code == 0
    assert not wait_for(world["mark"], timeout_s=0.5)


# `vg dream run`, `vg dream worker` and `vg dream status`


class FakeRunner:
    def __init__(self, result: DreamRun | None) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def __call__(
        self, graph_home: Path, cwd: Path, settings: DreamSettings, ports: object, **options: object
    ) -> DreamRun | None:
        self.calls.append({"graph_home": graph_home, "cwd": cwd, "settings": settings, **options})
        return self.result


RAN = DreamRun(
    status="ran",
    project_id="project",
    vault="proj-vault",
    judged=3,
    proposals=(
        DreamProposal(
            candidate_key="session:s1",
            action="remember",
            vault="proj-vault",
            vault_root="/vault",
            target="Embedding model",
            review_path="scratch/review/r1.md",
        ),
    ),
    outcomes={"proposed": 1, "none": 2},
    cost_usd=0.4567,
)


@pytest.fixture
def fake_runner(monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    fake = FakeRunner(RAN)
    monkeypatch.setattr(dream_worker, "run_dream_locked", fake)
    return fake


def test_run_is_a_manual_run_that_ignores_off(world: dict[str, Path], fake_runner: FakeRunner) -> None:
    arguments = ["dream", "run", "--graph-home", str(world["graph_home"]), "--vault-map", str(world["map"])]

    result = runner.invoke(app, [*arguments, "--cwd", str(world["project"]), "--dry-run"])

    assert result.exit_code == 0, result.output
    call = fake_runner.calls[0]
    assert (call["cwd"], call["manual"], call["dry_run"], call["lock_fd"]) == (world["project"], True, True, None)
    assert "dream: ran" in result.output
    assert "project: project vault: proj-vault" in result.output
    assert "judged: 3 outcomes: none=2 proposed=1" in result.output
    assert "cost_usd: 0.46" in result.output
    assert "proposal: remember Embedding model <- session:s1 [scratch/review/r1.md]" in result.output


def test_worker_does_nothing_while_dreaming_is_off(world: dict[str, Path], fake_runner: FakeRunner) -> None:
    arguments = ["dream", "worker", "--graph-home", str(world["graph_home"]), "--vault-map", str(world["map"])]

    off = runner.invoke(app, [*arguments, "--cwd", str(world["project"])])
    assert off.exit_code == 0, off.output
    assert "dream: skipped off" in off.output
    assert fake_runner.calls == []

    turn_on(world["graph_home"])
    on = runner.invoke(app, [*arguments, "--cwd", str(world["project"])])
    assert on.exit_code == 0, on.output
    assert (fake_runner.calls[0]["manual"], fake_runner.calls[0]["dry_run"]) == (False, False)


def test_run_reports_a_held_lock_a_failed_run_and_a_missing_map(
    world: dict[str, Path], fake_runner: FakeRunner
) -> None:
    arguments = ["dream", "run", "--graph-home", str(world["graph_home"]), "--cwd", str(world["project"])]

    fake_runner.result = None
    held = runner.invoke(app, [*arguments, "--vault-map", str(world["map"])])
    assert held.exit_code == 0
    assert "another dream run holds logs/dream-worker.lock" in held.output

    fake_runner.result = replace(RAN, status="failed", reason="judge_unavailable", message="claude cannot run")
    failed = runner.invoke(app, [*arguments, "--vault-map", str(world["map"])])
    assert failed.exit_code == 1
    assert "dream: failed judge_unavailable" in failed.output
    assert "message: claude cannot run" in failed.output

    missing = runner.invoke(app, [*arguments, "--vault-map", str(world["map"].parent / "none.json")])
    assert missing.exit_code == 1
    assert "dream: skipped no_vault_map" in missing.output


def test_status_counts_only_dream_proposals_and_says_why_dreaming_stopped(world: dict[str, Path]) -> None:
    graph_home = world["graph_home"]
    vault = world["map"].parent.parent.parent / "vaults" / "proj-vault"
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True)

    def item(name: str, status: str, kind: str = "memory-proposal") -> str:
        # The Vault's accept writes "Published:" into the resolution; without it an accept is not counted.
        resolution = 'resolution: "ok Published: wiki/a.md."\n' if status == "accepted" else ""
        (queue / name).write_text(f"---\ntype: {kind}\nstatus: {status}\n{resolution}---\n# item\n", encoding="utf-8")
        return f"scratch/review/{name}"

    sent = [item("a.md", "accepted"), item("b.md", "accepted"), item("c.md", "rejected"), item("d.md", "pending")]
    item("manual.md", "accepted")  # a manual proposal: not counted
    logs = graph_home / "logs"
    logs.mkdir(exist_ok=True)
    run_line = {
        "record": "run",
        "at": "2026-11-19T01:00:00Z",
        "project": "project",
        "vault": "proj-vault",
        "vault_root": str(vault),
        "status": "ran",
        "reason": None,
        "judged": 12,
        "proposals": 5,
    }
    proposal_lines = [
        {
            "record": "proposal",
            "project": "project",
            "candidate_key": f"session:s{index}",
            "vault": "proj-vault",
            "vault_root": str(vault),
            "review_path": path,
        }
        for index, path in enumerate([*sent, "scratch/review/gone.md"])
    ]
    (logs / "dream-runs.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in [*proposal_lines, run_line]), encoding="utf-8"
    )

    result = runner.invoke(app, ["dream", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "runs: 1" in result.output
    assert "last_run: project 2026-11-19T01:00:00Z ran judged=12 proposals=5" in result.output
    assert "proposals: sent=5 accepted=2 rejected=1 pending=1 unpublished=0 other=1" in result.output
    assert "acceptance_rate: 0.67 of 3 resolved" in result.output
    assert "stopped:" not in result.output

    for index in range(9):
        item(f"waiting-{index}.md", "pending")
    stopped = runner.invoke(app, ["dream", "status", "--graph-home", str(graph_home)])
    assert "stopped: pending cap reached in proj-vault (10 waiting, cap 10)" in stopped.output


def test_status_shows_the_pending_cap_stop_before_any_dream_proposal_exists(world: dict[str, Path]) -> None:
    graph_home = world["graph_home"]
    vault = world["map"].parent.parent.parent / "vaults" / "proj-vault"
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True)
    for index in range(10):  # ten manual proposals fill the cap
        (queue / f"manual-{index}.md").write_text(
            "---\ntype: memory-proposal\nstatus: pending\n---\n# item\n", encoding="utf-8"
        )
    skipped = {
        "record": "run",
        "at": "2026-11-19T01:00:00Z",
        "project": "project",
        "vault": "proj-vault",
        "vault_root": str(vault),
        "status": "skipped",
        "reason": "pending_cap",
        "judged": 0,
        "proposals": 0,
    }
    (graph_home / "logs").mkdir(exist_ok=True)
    (graph_home / "logs" / "dream-runs.jsonl").write_text(json.dumps(skipped) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["dream", "status", "--graph-home", str(graph_home)])

    assert "last_run: project 2026-11-19T01:00:00Z skipped pending_cap judged=0 proposals=0" in result.output
    assert "proposals: sent=0 accepted=0 rejected=0 pending=0 unpublished=0 other=0" in result.output
    assert "stopped: pending cap reached in proj-vault (10 waiting, cap 10)" in result.output
