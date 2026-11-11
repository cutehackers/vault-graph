"""Two-stage catch-up on a Graph Home without an index (spec 2026-11-11 §4.4.2, A-12).

The first session start after install finds registered Vaults without an index. The background
catch-up indexes them with ``vg index --no-vector`` first, so keyword search works within seconds,
and builds the vectors after that.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner, Result

from tests.test_cli_hook_session_start import FIXTURES, hook, invoke, l1_folder, render
from tests.test_cli_setup import _deterministic_text_embeddings
from vault_graph.interface.cli import hook_commands
from vault_graph.interface.cli.main import app
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.interface.mcp.mcp_tools import SearchVaultInput

runner = CliRunner()


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path.resolve()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root / "claude"))
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    for source in sorted((FIXTURES / "vaults").rglob("*.md")):
        target = root / "vaults" / source.relative_to(FIXTURES / "vaults")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(source.read_text(encoding="utf-8"), root), encoding="utf-8")
    (root / "map").mkdir()
    (root / "map" / "vault-map.json").write_text(
        render((FIXTURES / "vault-map.json").read_text(encoding="utf-8"), root), encoding="utf-8"
    )
    for repo in ("alpha", "both"):
        (root / "repos" / repo).mkdir(parents=True)
        subprocess.run(["git", "-C", str(root / "repos" / repo), "init", "-q"], check=True)
        l1_folder(root, repo).mkdir(parents=True)
    return root


def session_start(home: Path, base: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Result, list[dict[str, list[str]]]]:
    """Run the hook. Return its result and the plans of the catch-up processes, which are not started."""
    started: list[dict[str, list[str]]] = []
    real_popen = subprocess.Popen

    def recording_popen(command: list[str], **kwargs: object) -> object:
        if hook_commands._CATCH_UP_SCRIPT not in command:
            return real_popen(command, **kwargs)  # type: ignore[call-overload]
        started.append(json.loads(command[-1]))
        return SimpleNamespace(pid=4242)

    # Popen is patched only while the hook runs: the MCP package annotates with subprocess.Popen[bytes].
    with monkeypatch.context() as patch:
        patch.setattr("vault_graph.interface.cli.hook_commands.subprocess.Popen", recording_popen)
        result = hook(home, base)
    return result, started


def run_plan(
    home: Path, plan: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch, *, stop_at_vectors: bool = False
) -> list[list[str]]:
    """Run the catch-up body in this process. ``vg index --no-vector`` runs for real, vector runs are recorded."""
    calls: list[list[str]] = []

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = arguments[3:]
        calls.append(command)
        if "--no-vector" in command or not stop_at_vectors:
            result = runner.invoke(app, command)
            assert result.exit_code == 0, result.output
        return subprocess.CompletedProcess(arguments, 0)

    with monkeypatch.context() as patch:
        patch.setattr("vault_graph.interface.cli.hook_commands.subprocess.run", run)
        patch.setattr(hook_commands, "_wait_for_gate", lambda descriptor, *, timeout_s: True)
        patch.setattr(sys, "argv", ["-c", str(home), "0", json.dumps(plan)])
        hook_commands.run_catch_up_index()
    return calls


def test_catch_up_runs_every_keyword_index_before_any_vector_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments[3:])
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.subprocess.run", run)
    monkeypatch.setattr(hook_commands, "_wait_for_gate", lambda descriptor, *, timeout_s: True)
    monkeypatch.setattr(hook_commands, "vectors_need_catch_up", lambda graph_home, vault_id: True)
    plan = {"first": ["new-a", "new-b"], "index": ["changed"], "check": ["old"]}
    monkeypatch.setattr(sys, "argv", ["-c", str(tmp_path), "0", json.dumps(plan)])

    hook_commands.run_catch_up_index()

    home = str(tmp_path)
    assert calls == [
        ["index", "--graph-home", home, "--vault-id", "new-a", "--no-vector"],
        ["index", "--graph-home", home, "--vault-id", "new-b", "--no-vector"],
        ["index", "--graph-home", home, "--vault-id", "new-a"],
        ["index", "--graph-home", home, "--vault-id", "new-b"],
        ["index", "--graph-home", home, "--vault-id", "changed"],
        ["index", "--graph-home", home, "--vault-id", "old"],
    ]


def test_a_plan_without_first_vaults_still_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A catch-up started by the previous version has no ``first`` key."""
    calls: list[list[str]] = []

    def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments[3:])
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.subprocess.run", run)
    monkeypatch.setattr(hook_commands, "_wait_for_gate", lambda descriptor, *, timeout_s: True)
    monkeypatch.setattr(sys, "argv", ["-c", str(tmp_path), "0", json.dumps({"index": ["main"], "check": []})])

    hook_commands.run_catch_up_index()

    assert calls == [["index", "--graph-home", str(tmp_path), "--vault-id", "main"]]


def test_search_gives_keyword_results_and_a_vector_unavailable_warning_after_the_first_stage(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = base / "graph-home"
    invoke("init", "--vault", str(base / "vaults" / "main"), "--vault-id", "main", "--graph-home", str(home))
    _, plans = session_start(home, base, monkeypatch)

    calls = run_plan(home, plans[0], monkeypatch, stop_at_vectors=True)

    assert calls[0][-1] == "--no-vector"
    body = create_mcp_server(McpServerConfig(graph_home_path=home)).tool_registry.search_vault(
        SearchVaultInput(query="SQLite")
    )
    assert body.payload["results"], body.text
    assert "vector_unavailable" in {warning.code for warning in body.warnings}


def test_the_second_session_start_after_both_stages_recalls_and_plans_no_keyword_index(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = base / "graph-home"
    invoke("init", "--vault", str(base / "vaults" / "main"), "--vault-id", "main", "--graph-home", str(home))
    _, plans = session_start(home, base, monkeypatch)
    run_plan(home, plans[0], monkeypatch)

    result, plans = session_start(home, base, monkeypatch)

    assert result.exit_code == 0, result.output
    assert plans == [{"first": [], "index": [], "check": ["main"]}]
