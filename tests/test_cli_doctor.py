"""`vg doctor` reports each problem with one fix command and changes nothing (spec 2026-11-11 §4.4.1, §6, A-2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_setup import _deterministic_text_embeddings
from vault_graph.interface.cli.main import app

runner = CliRunner()

_FAILURE_ENTRY = {
    "vault_id": "default",
    "error_digest": "0123456789abcdef",
    "error_head": "model unavailable",
    "first_failed_at": "2026-11-10T00:00:00+00:00",
    "last_failed_at": "2026-11-11T00:00:00+00:00",
    "count": 2,
}


@pytest.fixture
def model_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.doctor_commands.embedding_model_downloaded", lambda *_: True)


@pytest.fixture
def model_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.doctor_commands.embedding_model_downloaded", lambda *_: False)


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault


def _init(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    result = runner.invoke(app, ["init", "--vault", str(_vault(tmp_path)), "--graph-home", str(state)])
    assert result.exit_code == 0, result.output
    return state


def _indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = _init(tmp_path)
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    result = runner.invoke(app, ["index", "--graph-home", str(state)])
    assert result.exit_code == 0, result.output
    return state


def _claude_config(tmp_path: Path, *, registered: bool) -> Path:
    path = tmp_path / "claude.json"
    servers = {"vault-graph": {"type": "stdio", "command": "/bin/vg", "args": ["serve", "--mcp"]}} if registered else {}
    path.write_text(json.dumps({"mcpServers": {"other": {}, **servers}}), encoding="utf-8")
    return path


def _write_failure(state: Path) -> None:
    path = state / "logs" / "vector-index-failures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"failures": [_FAILURE_ENTRY]}), encoding="utf-8")


def _doctor(state: Path, config: Path, *extra: str) -> tuple[int, list[str]]:
    result = runner.invoke(
        app, ["doctor", "--graph-home", str(state), "--mcp-config-path", str(config), "--agent", "claude", *extra]
    )
    return result.exit_code, result.stdout.splitlines()


def _fix_after(lines: list[str], problem_prefix: str) -> str:
    """Return the fix line that follows the one problem line starting with `problem_prefix`."""
    positions = [index for index, line in enumerate(lines) if line.startswith(problem_prefix)]
    assert len(positions) == 1, lines
    fix = lines[positions[0] + 1]
    assert fix.startswith("fix: "), lines
    return fix


def _tree_digest(*roots: Path) -> dict[str, str]:
    digest: dict[str, str] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            key = str(path)
            digest[key] = "dir" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def test_doctor_reports_no_problem_when_everything_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_present: None
) -> None:
    state = _indexed(tmp_path, monkeypatch)

    exit_code, lines = _doctor(state, _claude_config(tmp_path, registered=True))

    assert exit_code == 0, lines
    assert not [line for line in lines if line.startswith(("problem:", "fix:"))]
    assert "ok: no problems found" in lines


def test_doctor_reports_failure_record_with_index_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_present: None
) -> None:
    state = _indexed(tmp_path, monkeypatch)
    _write_failure(state)

    exit_code, lines = _doctor(state, _claude_config(tmp_path, registered=True))

    assert exit_code == 1
    problem = next(line for line in lines if line.startswith("problem: index_failed"))
    assert "vault_id=default" in problem
    assert "count=2" in problem
    assert "model unavailable" in problem
    assert _fix_after(lines, "problem: index_failed") == (
        f"fix: vg index --vault-id default --graph-home {state.resolve()}"
    )


def test_doctor_reports_missing_index_with_index_command(tmp_path: Path, model_present: None) -> None:
    state = _init(tmp_path)

    exit_code, lines = _doctor(state, _claude_config(tmp_path, registered=True))

    assert exit_code == 1
    assert _fix_after(lines, "problem: index_missing vault_id=default") == (
        f"fix: vg index --vault-id default --graph-home {state.resolve()}"
    )


def test_doctor_reports_missing_model_files_with_download_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_absent: None
) -> None:
    state = _indexed(tmp_path, monkeypatch)

    exit_code, lines = _doctor(state, _claude_config(tmp_path, registered=True))

    assert exit_code == 1
    fix = _fix_after(lines, "problem: embedding_model_missing model=arctic-m")
    assert fix.startswith("fix: vg embedding use arctic-m --models-dir ")
    assert fix.endswith(f" --graph-home {state.resolve()}")


@pytest.mark.parametrize("config_exists", [True, False])
def test_doctor_reports_unregistered_mcp_with_register_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_present: None, config_exists: bool
) -> None:
    state = _indexed(tmp_path, monkeypatch)
    config = _claude_config(tmp_path, registered=False) if config_exists else tmp_path / "missing.json"

    exit_code, lines = _doctor(state, config)

    assert exit_code == 1
    assert _fix_after(lines, "problem: mcp_not_registered agent=claude") == (
        f"fix: vg mcp register --agent claude --graph-home {state.resolve()} --config-path {config}"
    )


def test_doctor_reads_codex_toml_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_present: None
) -> None:
    state = _indexed(tmp_path, monkeypatch)
    config = tmp_path / "config.toml"
    config.write_text('[mcp_servers.vault-graph]\ncommand = "vg"\nargs = ["serve", "--mcp"]\n', encoding="utf-8")

    registered = runner.invoke(
        app, ["doctor", "--graph-home", str(state), "--agent", "codex", "--mcp-config-path", str(config)]
    )
    config.write_text('[mcp_servers.other]\ncommand = "other"\n', encoding="utf-8")
    unregistered = runner.invoke(
        app, ["doctor", "--graph-home", str(state), "--agent", "codex", "--mcp-config-path", str(config)]
    )

    assert registered.exit_code == 0, registered.output
    assert unregistered.exit_code == 1
    assert "problem: mcp_not_registered agent=codex" in unregistered.stdout


def test_doctor_reports_uninitialized_graph_home_without_creating_it(tmp_path: Path, model_present: None) -> None:
    state = tmp_path / "state"

    exit_code, lines = _doctor(state, _claude_config(tmp_path, registered=True))

    assert exit_code == 1
    assert _fix_after(lines, "problem: graph_home_not_initialized") == (
        f"fix: vg setup --vault <Vault 경로> --graph-home {state.resolve()} --agent claude --mcp"
    )
    assert not state.exists()


def test_doctor_changes_no_file_in_vault_or_graph_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model_absent: None
) -> None:
    state = _indexed(tmp_path, monkeypatch)
    runner.invoke(app, ["vault", "add", "second", "--path", str(_second_vault(tmp_path)), "--graph-home", str(state)])
    _write_failure(state)
    config = _claude_config(tmp_path, registered=False)
    roots = (tmp_path / "vault", tmp_path / "second", state)
    before = _tree_digest(*roots)

    exit_code, lines = _doctor(state, config)

    assert exit_code == 1
    for prefix in (
        "problem: index_failed",
        "problem: index_missing vault_id=second",
        "problem: embedding_model_missing",
        "problem: mcp_not_registered",
    ):
        _fix_after(lines, prefix)
    assert _tree_digest(*roots) == before


def _second_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "second"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "other.md").write_text("# Other\n", encoding="utf-8")
    return vault
