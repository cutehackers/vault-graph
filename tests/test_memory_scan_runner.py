"""Read-only Vault ``memory-scan --json`` run and its reconcile with the vg L1 check (spec 2026-11-05 §4.4.5).

Covers A-24 (adapter part) and A-31 (L1 folder and Vault files unchanged).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from vault_graph.interface.composition.adapters.auto_memory_reader import memory_folder_key
from vault_graph.interface.composition.adapters.memory_scan_runner import (
    MemoryScanOutcome,
    memory_scan_path,
    run_memory_scan,
    scan_linked_vaults,
    scan_vault_memory,
)

FAKE_CLI = """
import json, os, pathlib, sys, time
here = pathlib.Path(__file__).resolve().parent
if sys.argv[1:] != ["memory-scan", "--json"] or not sys.flags.isolated or not sys.flags.dont_write_bytecode:
    print("unexpected command: " + " ".join(sys.argv), file=sys.stderr)
    sys.exit(3)
mode = os.environ.get("FAKE_SCAN_MODE", "ok")
if mode == "fail":
    print("No vault map at /nowhere.", file=sys.stderr)
    sys.exit(1)
if mode == "sleep":
    time.sleep(10)
if mode == "garbage":
    print("not json")
    sys.exit(0)
report = json.loads(os.environ["FAKE_SCAN_REPORT"])
report["seen_cwd"] = os.getcwd()
report["seen_config_dir"] = os.environ.get("CLAUDE_CONFIG_DIR")
print(json.dumps(report, indent=2))
"""

PROJECT = "proj"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree_state(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class Setup:
    def __init__(self, tmp_path: Path) -> None:
        self.config = tmp_path / "config"
        self.vault = tmp_path / "vault"
        self.graph_home = tmp_path / "graph-home"
        self.project_root = str(tmp_path / "repo")
        self.memory = self.config / "projects" / memory_folder_key(self.project_root) / "memory"
        _write(self.vault / "tools" / "wiki" / "cli.py", FAKE_CLI)
        _write(self.memory / "MEMORY.md", "- [kept](kept.md)\n")
        _write(self.memory / "kept.md", "kept note\n")
        _write(self.memory / "fresh.md", "fresh note\n")
        _write(
            self.vault / "wiki" / "sources" / "kept-source.md", f"---\nraw_sha256: {_sha('kept note' + chr(10))}\n---\n"
        )
        self.map_path = _write(
            self.config / "vault-builder" / "vault-map.json",
            json.dumps(
                {
                    "version": 2,
                    "vaults": {"main": {"path": str(self.vault), "role": "project"}},
                    "projects": {PROJECT: {"root": self.project_root, "vaults": ["main"]}},
                }
            ),
        )
        self.environ = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), "HOME": str(tmp_path)}

    def vault_report(self, *, fresh_imported: bool = False) -> dict[str, object]:
        def note(name: str, text: str, imported: bool) -> dict[str, object]:
            return {"name": name, "path": str(self.memory / name), "sha256": _sha(text), "imported": imported}

        return {
            "vault_name": "main",
            "projects": [
                {
                    "id": PROJECT,
                    "memory_dir": str(self.memory),
                    "notes": [note("fresh.md", "fresh note\n", fresh_imported), note("kept.md", "kept note\n", True)],
                }
            ],
        }

    def scan(
        self, *, report: dict[str, object] | None = None, mode: str = "ok", timeout_s: float = 20
    ) -> MemoryScanOutcome | None:
        self.environ["FAKE_SCAN_MODE"] = mode
        self.environ["FAKE_SCAN_REPORT"] = json.dumps(report if report is not None else self.vault_report())
        return scan_vault_memory(
            vault_id="vault-a",
            vault_root=self.vault,
            vault_map_path=self.map_path,
            graph_home=self.graph_home,
            environ=self.environ,
            managed_settings_path=None,
            timeout_s=timeout_s,
        )


def test_run_memory_scan_returns_the_vault_report_run_in_the_vault_with_the_config_dir(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.environ["FAKE_SCAN_REPORT"] = json.dumps(setup.vault_report())

    run = run_memory_scan(setup.vault, timeout_s=20, environ=setup.environ)

    assert run.problem is None
    assert run.report is not None
    assert Path(str(run.report["seen_cwd"])).resolve() == setup.vault.resolve()
    assert run.report["seen_config_dir"] == str(setup.config)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("fail", "exit code 1: No vault map at /nowhere."), ("garbage", "no memory-scan JSON report")],
)
def test_run_memory_scan_reports_a_failed_run(tmp_path: Path, mode: str, expected: str) -> None:
    setup = Setup(tmp_path)
    setup.environ["FAKE_SCAN_MODE"] = mode

    run = run_memory_scan(setup.vault, timeout_s=20, environ=setup.environ)

    assert run.report is None
    assert run.problem is not None and expected in run.problem


def test_run_memory_scan_stops_after_the_time_limit(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.environ["FAKE_SCAN_MODE"] = "sleep"

    run = run_memory_scan(setup.vault, timeout_s=0.5, environ=setup.environ)

    assert run.problem is not None and "did not finish in 0.5 seconds" in run.problem


def test_run_memory_scan_without_vault_tools(tmp_path: Path) -> None:
    run = run_memory_scan(tmp_path, timeout_s=5, environ={})

    assert run.problem is not None and "tools/wiki/cli.py" in run.problem


def test_agreeing_scan_is_saved_in_graph_home_without_a_warning(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    outcome = setup.scan()

    assert outcome is not None
    assert outcome.warning is None
    assert [(note.name, note.imported) for note in outcome.notes] == [("fresh.md", False), ("kept.md", True)]
    assert [note.sha256 for note in outcome.unimported] == [_sha("fresh note\n")]
    saved = memory_scan_path(setup.graph_home, "vault-a")
    assert saved == setup.graph_home / "memory" / "memory-scan-vault-a.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["projects"][0]["id"] == PROJECT


def test_disagreeing_scan_uses_the_vault_result_and_one_warning_line(tmp_path: Path) -> None:
    setup = Setup(tmp_path)

    outcome = setup.scan(report=setup.vault_report(fresh_imported=True))

    assert outcome is not None
    assert all(note.imported for note in outcome.notes)
    assert outcome.unimported == ()
    assert outcome.warning is not None
    assert "\n" not in outcome.warning
    assert "vault-a" in outcome.warning and "1 L1 note" in outcome.warning


def test_failed_scan_uses_the_vg_check_warns_once_and_drops_an_old_result(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.scan()
    saved = memory_scan_path(setup.graph_home, "vault-a")
    assert saved.is_file()

    outcome = setup.scan(mode="fail")

    assert outcome is not None
    assert [(note.name, note.imported) for note in outcome.notes] == [("fresh.md", False), ("kept.md", True)]
    assert outcome.warning is not None and "\n" not in outcome.warning
    assert "using the vg sha256 check only" in outcome.warning
    assert not saved.exists()


def test_l1_folder_and_vault_files_keep_sha256_and_mtime(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    memory_before = _tree_state(setup.memory)
    vault_before = _tree_state(setup.vault)

    setup.scan()
    setup.scan(report=setup.vault_report(fresh_imported=True))
    setup.scan(mode="fail")

    assert _tree_state(setup.memory) == memory_before
    assert _tree_state(setup.vault) == vault_before


def test_vault_without_linked_projects_or_outside_the_map_is_skipped(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    other = tmp_path / "other-vault"
    other.mkdir()
    setup.environ["FAKE_SCAN_REPORT"] = json.dumps(setup.vault_report())

    outcomes = scan_linked_vaults(
        [("other", other), ("vault-a", setup.vault)],
        vault_map_path=setup.map_path,
        graph_home=setup.graph_home,
        environ=setup.environ,
        managed_settings_path=None,
        timeout_s=20,
    )

    assert [outcome.vault_id for outcome in outcomes] == ["vault-a"]
    assert not memory_scan_path(setup.graph_home, "other").exists()


def test_missing_vault_map_scans_nothing(tmp_path: Path) -> None:
    outcomes = scan_linked_vaults(
        [("vault-a", tmp_path)],
        vault_map_path=tmp_path / "absent.json",
        graph_home=tmp_path / "graph-home",
        environ={},
        managed_settings_path=None,
        timeout_s=5,
    )

    assert outcomes == ()


_VAULT_BUILDER = Path(os.environ.get("VAULT_BUILDER_ROOT", Path.home() / "workspace" / "vault-builder"))


@pytest.mark.skipif(
    not (_VAULT_BUILDER / "tools" / "wiki" / "lib" / "memory_scan.py").is_file(),
    reason="vault-builder checkout not found; set VAULT_BUILDER_ROOT",
)
def test_real_vault_memory_scan_agrees_with_the_vg_check(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    shutil.rmtree(setup.vault / "tools")
    shutil.copytree(
        _VAULT_BUILDER / "tools", setup.vault / "tools", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    memory_before = _tree_state(setup.memory)

    outcome = scan_vault_memory(
        vault_id="vault-a",
        vault_root=setup.vault,
        vault_map_path=setup.map_path,
        graph_home=setup.graph_home,
        environ=setup.environ,
        managed_settings_path=None,
        timeout_s=60,
        python_executable=sys.executable,
    )

    assert outcome is not None
    assert outcome.warning is None
    assert [(note.name, note.imported) for note in outcome.notes] == [("fresh.md", False), ("kept.md", True)]
    assert memory_scan_path(setup.graph_home, "vault-a").is_file()
    assert _tree_state(setup.memory) == memory_before


def test_index_run_keeps_the_scan_in_graph_home_and_leaves_vault_and_l1_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from tests.test_multi_vault_identity import _fake_text_embeddings
    from vault_graph.interface.cli.main import app

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _fake_text_embeddings)
    setup = Setup(tmp_path)
    _write(setup.vault / "wiki" / "page.md", "# Page\nBody\n")
    for name, value in {
        "CLAUDE_CONFIG_DIR": str(setup.config),
        "VAULT_GRAPH_VAULT_MAP": str(setup.map_path),
        "FAKE_SCAN_REPORT": json.dumps(setup.vault_report(fresh_imported=True)),
    }.items():
        monkeypatch.setenv(name, value)
    runner = CliRunner()
    init = runner.invoke(
        app, ["init", "--vault-id", "vault-a", "--vault", str(setup.vault), "--graph-home", str(setup.graph_home)]
    )
    assert init.exit_code == 0, init.output
    memory_before = _tree_state(setup.memory)
    vault_before = _tree_state(setup.vault)

    result = runner.invoke(app, ["index", "--graph-home", str(setup.graph_home)])

    assert result.exit_code == 0, result.output
    assert memory_scan_path(setup.graph_home, "vault-a").is_file()
    assert "memory-scan for Vault vault-a disagrees with the vg check on 1 L1 note(s)" in result.stderr
    assert _tree_state(setup.memory) == memory_before
    assert _tree_state(setup.vault) == vault_before
