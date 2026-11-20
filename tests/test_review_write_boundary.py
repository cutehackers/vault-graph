"""Only `vg review` reaches the Vault's ``review resolve``, and the review flow writes nothing itself.

Spec 2026-11-20 A5.

Covers D1, I1 and I2: the import of ``vault_review_cli``, the MCP tool names, the write calls in the three review
modules, and the Vault file hashes around an accept and a reject run with a stand-in adapter.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.interface.cli import review_commands
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.vault_review_cli import ReviewResolveOutcome

SRC = Path(__file__).parents[1] / "src" / "vault_graph"
ADAPTER = "vault_graph.interface.composition.adapters.vault_review_cli"
REVIEW_COMMANDS = "vault_graph.interface.cli.review_commands"
ONLY_IMPORTER = "interface/cli/review_commands.py"
# The three modules of the review flow that must not write: they read the Vault and build what is shown.
READ_ONLY_MODULES = (
    "interface/cli/review_commands.py",
    "interface/composition/adapters/vault_review_queue.py",
    "operation/memory/proposal_change.py",
)
WRITE_CALLS = frozenset(
    {
        "write_text",
        "write_bytes",
        "open",
        "touch",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "symlink_to",
        "chmod",
        "rmtree",
        "copy",
        "copyfile",
        "copytree",
        "move",
        "run",
        "Popen",
        "check_call",
        "check_output",
        "system",
    }
)
WRITE_MODULES = frozenset({"subprocess", "shutil", "tempfile"})
REVIEW_TOOL_WORDS = frozenset({"accept", "reject", "resolve", "review", "approve"})

runner = CliRunner()


def imported_modules(path: Path) -> set[str]:
    """Every module a file imports, with ``from package import name`` also counted as ``package.name``."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_only_review_commands_imports_the_review_resolve_adapter() -> None:
    importers = sorted(path.relative_to(SRC).as_posix() for path in source_files() if ADAPTER in imported_modules(path))

    assert importers == [ONLY_IMPORTER]


def test_no_other_source_file_names_the_adapter_even_as_text() -> None:
    """A dynamic import (``importlib``, ``__import__``) would need the module name as text."""
    named = sorted(
        path.relative_to(SRC).as_posix()
        for path in source_files()
        if path.name != "vault_review_cli.py" and "vault_review_cli" in path.read_text(encoding="utf-8")
    )

    assert named == [ONLY_IMPORTER]


def test_only_the_cli_entry_module_imports_review_commands() -> None:
    importers = sorted(
        path.relative_to(SRC).as_posix() for path in source_files() if REVIEW_COMMANDS in imported_modules(path)
    )

    assert importers == ["interface/cli/main.py"]


def test_no_mcp_tool_accepts_or_rejects_a_proposal() -> None:
    tool_names: list[str] = []
    for path in sorted((SRC / "interface" / "mcp").rglob("*.py")):
        tool_names.extend(re.findall(r'@server\.tool\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
        assert not {ADAPTER, REVIEW_COMMANDS} & imported_modules(path), path

    assert "remember" in tool_names and "search_vault" in tool_names
    offending = [name for name in tool_names if REVIEW_TOOL_WORDS & set(name.split("_"))]
    assert offending == []


@pytest.mark.parametrize("module", READ_ONLY_MODULES)
def test_the_review_modules_hold_no_write_call(module: str) -> None:
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }

    assert calls & WRITE_CALLS == set()
    assert {name.split(".")[0] for name in imported_modules(SRC / module)} & WRITE_MODULES == set()


def digest(root: Path) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_accept_and_reject_with_a_stand_in_adapter_leave_every_vault_file_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stand-in writes nothing, so any changed Vault file would be a write by vault-graph itself (I1)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("VAULT_GRAPH_FACTS_CHILD", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    vault = tmp_path / "vaults" / "proj-vault"
    queue = vault / "scratch" / "review"
    queue.mkdir(parents=True)
    (vault / "wiki").mkdir()
    (vault / "wiki" / "page.md").write_text("---\ntitle: Page\n---\n# Page\n", encoding="utf-8")
    draft = {"operation": "patch-page", "path": "wiki/page.md", "frontmatter": {"status": "retired"}}
    for review_id in ("p1", "p2"):
        (queue / f"{review_id}.md").write_text(
            f"---\nreview_id: {review_id}\ntype: memory-proposal\nstatus: pending\nsummary: 폐기한다\n"
            'resolution: ""\ntarget_path: wiki/page.md\n---\n# 폐기한다\n',
            encoding="utf-8",
        )
        (queue / f"{review_id}.draft.json").write_text(json.dumps(draft), encoding="utf-8")
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"proj-vault": {"path": str(vault), "role": "personal"}},
                "projects": {"project": {"root": str(project), "vaults": ["proj-vault"]}},
            }
        ),
        encoding="utf-8",
    )
    graph_home = home / ".vault-graph"
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)]).exit_code == 0
    calls: list[tuple[str, str]] = []
    index_calls: list[tuple[str, ...]] = []

    class StandInCli:
        def resolve(self, vault_root: Path, review_path: str, *, status: str, resolution: str) -> ReviewResolveOutcome:
            calls.append((review_path, status))
            return ReviewResolveOutcome("resolved", written_paths=("wiki/page.md",) if status == "accepted" else ())

    def no_index(_graph_home: Path, index_vault_ids: tuple[str, ...]) -> None:
        index_calls.append(index_vault_ids)

    monkeypatch.setattr(review_commands, "VaultReviewCli", StandInCli)
    monkeypatch.setattr(review_commands, "start_catch_up_index", no_index)
    common = ["--cwd", str(project), "--graph-home", str(graph_home), "--vault-map", str(vault_map)]
    vault_before, graph_home_before = digest(vault), digest(graph_home)

    accepted = runner.invoke(app, ["review", "accept", "p1", *common])
    rejected = runner.invoke(app, ["review", "reject", "p2", "--reason", "틀림", *common])

    assert accepted.exit_code == 0, accepted.output
    assert rejected.exit_code == 0, rejected.output
    assert calls == [("scratch/review/p1.md", "accepted"), ("scratch/review/p2.md", "rejected")]
    assert index_calls == [("default",)]
    assert digest(vault) == vault_before
    assert digest(graph_home) == graph_home_before
