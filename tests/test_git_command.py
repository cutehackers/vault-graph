"""One git runner in M01 for the vault map (M17) and the code scanner (M11) (정리 발견5)."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from vault_graph.operation.scope.git_command import run_git

SRC = Path(__file__).resolve().parents[1] / "src" / "vault_graph"


def test_run_git_returns_stripped_output_empty_output_and_none_on_failure(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)

    assert run_git(tmp_path, "rev-parse", "--show-toplevel") == str(tmp_path.resolve())
    assert run_git(tmp_path, "status", "--porcelain") == ""
    assert run_git(tmp_path, "rev-parse", "HEAD") is None
    assert run_git(tmp_path / "missing", "status") is None


def test_no_other_module_runs_git_itself() -> None:
    owners = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name in {"_git", "run_git"}
    )
    assert owners == ["operation/scope/git_command.py"]
