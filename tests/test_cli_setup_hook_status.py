from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_setup import _deterministic_text_embeddings
from tests.test_vault_map import make_vaults, render_fixture
from vault_graph.interface.cli.main import app, setup
from vault_graph.operation.integration import hook_status
from vault_graph.operation.integration.hook_status import claude_config_dir, vault_hooks_path

runner = CliRunner()


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_hooks(config_dir: Path, vg: object) -> Path:
    path = config_dir / "vault-builder" / "vault-hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "vg": vg}), encoding="utf-8")
    return path


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "claude"
    folder.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))
    return folder


@pytest.fixture
def running_vg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vg = _executable(tmp_path / "bin" / "vg")
    monkeypatch.setattr(hook_status, "running_vg_path", lambda: vg)
    return vg


def _run_setup(tmp_path: Path, agent: str = "claude") -> tuple[int, list[str]]:
    vault_root = tmp_path / "vault"
    vault_root.mkdir(exist_ok=True)
    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(vault_root),
            "--graph-home",
            str(tmp_path / "state"),
            "--agent",
            agent,
            "--dry-run",
        ],
    )
    warnings = [line for line in result.stderr.splitlines() if line.startswith("warning: hook_")]
    return result.exit_code, warnings


def test_config_dir_uses_claude_config_dir_then_home(tmp_path: Path) -> None:
    assert claude_config_dir(environ={"CLAUDE_CONFIG_DIR": str(tmp_path)}) == tmp_path
    assert claude_config_dir(environ={"CLAUDE_CONFIG_DIR": ""}) == Path.home() / ".claude"
    assert claude_config_dir(environ={}) == Path.home() / ".claude"
    assert vault_hooks_path(environ={"CLAUDE_CONFIG_DIR": str(tmp_path)}) == (
        tmp_path / "vault-builder" / "vault-hooks.json"
    )


def test_setup_warns_when_hooks_are_not_installed(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert len(warnings) == 1
    assert "hook_not_installed" in warnings[0]
    assert "vault-builder setup" in warnings[0]


def test_setup_for_codex_has_no_hook_warning_even_without_hook_settings(
    tmp_path: Path, config_dir: Path, running_vg: Path
) -> None:
    assert not (config_dir / "vault-builder" / "vault-hooks.json").exists()

    exit_code, warnings = _run_setup(tmp_path, agent="codex")

    assert exit_code == 0
    assert warnings == []


@pytest.mark.parametrize("vg_value", [None, "", "relative/vg", "/no/such/vg"])
def test_setup_warns_when_hooks_cannot_find_vg(
    tmp_path: Path, config_dir: Path, running_vg: Path, vg_value: object
) -> None:
    _write_hooks(config_dir, vg_value)

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert len(warnings) == 1
    assert "hook_vg_not_found" in warnings[0]
    assert "vault-builder setup" in warnings[0]


def test_setup_warns_when_hook_vg_is_not_executable(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    plain = tmp_path / "other" / "vg"
    plain.parent.mkdir()
    plain.write_text("", encoding="utf-8")
    plain.chmod(0o644)
    _write_hooks(config_dir, str(plain))

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert len(warnings) == 1
    assert "hook_vg_not_found" in warnings[0]


def test_setup_warns_when_hooks_use_another_vg(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    other = _executable(tmp_path / "other" / "vg")
    _write_hooks(config_dir, str(other))

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert len(warnings) == 1
    assert "hook_vg_differs" in warnings[0]
    assert "vault-builder setup" in warnings[0]


def test_setup_has_no_hook_warning_when_hooks_use_this_vg(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    _write_hooks(config_dir, str(running_vg))

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert warnings == []


def test_setup_treats_symlinked_hook_vg_as_the_same_vg(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    link = tmp_path / "local-bin" / "vg"
    link.parent.mkdir()
    os.symlink(running_vg, link)
    _write_hooks(config_dir, str(link))

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert warnings == []


def test_setup_reports_invalid_hook_json_as_a_warning_and_keeps_going(
    tmp_path: Path, config_dir: Path, running_vg: Path
) -> None:
    path = config_dir / "vault-builder" / "vault-hooks.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    (tmp_path / "vault").mkdir()

    result = runner.invoke(
        app,
        [
            "setup",
            "--vault",
            str(tmp_path / "vault"),
            "--graph-home",
            str(tmp_path / "state"),
            "--agent",
            "claude",
            "--dry-run",
            "--print-mcp-config",
        ],
    )

    assert result.exit_code == 0
    assert "mcp_config:" in result.stdout
    assert "warning: hook_" not in result.stdout
    warnings = [line for line in result.stderr.splitlines() if line.startswith("warning: hook_")]
    assert len(warnings) == 1
    assert "hook_settings_unreadable" in warnings[0]
    assert "vault-builder setup" in warnings[0]


def test_setup_keeps_failure_exit_code_and_still_reports_hooks(
    tmp_path: Path, config_dir: Path, running_vg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    base = tmp_path.resolve()
    make_vaults(base)
    (base / "vaults" / "team" / "wiki" / "page.md").write_text("# team\nteam evidence\n", encoding="utf-8")
    map_path = render_fixture("vault-map-v2.json", base)
    shutil.rmtree(base / "vaults" / "personal")
    graph_home = base / "graph-home"

    result = runner.invoke(
        app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(map_path), "--agent", "claude"]
    )

    assert result.exit_code == 1, result.output
    lines = result.stdout.splitlines()
    assert "vault_id: team" in lines
    assert any(line.startswith("setup_failed:") for line in lines)
    assert [line for line in result.stderr.splitlines() if line.startswith("warning: hook_")][0].startswith(
        "warning: hook_not_installed"
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_setup_does_not_write_hook_settings_or_claude_settings(
    tmp_path: Path, config_dir: Path, running_vg: Path
) -> None:
    hooks = _write_hooks(config_dir, "/no/such/vg")
    settings = config_dir / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": []}}), encoding="utf-8")
    before = (_digest(hooks), _digest(settings))

    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert len(warnings) == 1
    assert (_digest(hooks), _digest(settings)) == before


def test_setup_agent_default_stays_codex() -> None:
    agent_default = inspect.signature(setup).parameters["agent"].default
    assert agent_default.default == "codex"


def test_fix_command_names_the_running_vg_so_the_hooks_record_it(tmp_path: Path) -> None:
    vg = tmp_path / "with space" / "vg"

    assert hook_status.fix_command(vg) == f"VAULT_GRAPH_BIN='{vg}' vault-builder setup"
    assert hook_status.fix_command(None) == "vault-builder setup"


def test_a_hook_warning_names_the_running_vg(tmp_path: Path, config_dir: Path, running_vg: Path) -> None:
    exit_code, warnings = _run_setup(tmp_path)

    assert exit_code == 0
    assert f"VAULT_GRAPH_BIN={running_vg} vault-builder setup" in warnings[0]
