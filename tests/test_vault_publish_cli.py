"""The publish-draft subprocess adapter (spec 4.2.4) and the optional A-14 run on a copied Vault.

A-14 runs only when Vault tools are available. It copies them into a temporary directory and
never touches the user's real Vault.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

from tests.test_read_only_boundary import file_bytes
from vault_graph.interface.composition.adapters.vault_publish_cli import CLI_RELATIVE_PATH, VaultPublishCli
from vault_graph.operation.memory.memory_drafts import build_draft
from vault_graph.operation.memory.memory_requests import RememberRequest
from vault_graph.operation.memory.memory_write_service import MemoryWriteService
from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault

VAULT_TEMPLATE_ENV = "VAULT_GRAPH_TEST_VAULT_TEMPLATE"


def fake_vault(tmp_path: Path, script: str) -> Path:
    vault_root = tmp_path / "vault"
    cli = vault_root / CLI_RELATIVE_PATH
    cli.parent.mkdir(parents=True)
    cli.write_text(script, encoding="utf-8")
    return vault_root


def draft_file(tmp_path: Path) -> Path:
    draft = tmp_path / "drafts" / "draft.json"
    draft.parent.mkdir()
    draft.write_text("{}", encoding="utf-8")
    return draft


ECHO_ARGS = """
import os, sys
print("argv=" + "|".join(sys.argv[1:]))
print("cwd=" + os.getcwd())
print("flags=" + str(sys.flags.isolated) + str(sys.flags.dont_write_bytecode))
"""


def test_runs_publish_draft_with_the_draft_path_only_from_the_vault_root(tmp_path: Path) -> None:
    script = ECHO_ARGS + 'print("Validated draft: wiki/decisions/a.md")\nprint("Applied draft: wiki/decisions/a.md")\n'
    vault_root = fake_vault(tmp_path, script)
    draft = draft_file(tmp_path)

    outcome = VaultPublishCli().publish_draft(vault_root, draft, timeout_s=30)

    assert outcome.status == "published"
    assert outcome.written_paths == ("wiki/decisions/a.md",)
    assert f"argv=publish-draft|{draft}" in outcome.messages
    assert f"cwd={vault_root.resolve()}" in outcome.messages
    assert "flags=11" in outcome.messages
    assert not any("--report" in message for message in outcome.messages)


def test_non_zero_exit_is_rejected_with_the_output(tmp_path: Path) -> None:
    script = 'import sys\nprint("Draft failed validation:\\n[error] missing-field", file=sys.stderr)\nsys.exit(1)\n'
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish_draft(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.written_paths == ()
    assert "[error] missing-field" in outcome.messages


def test_lint_failure_before_the_write_is_explained(tmp_path: Path) -> None:
    script = 'import sys\nprint("Publish aborted: wiki lint must be clean before applying a draft.")\nsys.exit(1)\n'
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish_draft(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "rejected"
    assert any("Vault lint was already failing" in message for message in outcome.messages)


def test_timeout_stops_the_process_and_is_an_error(tmp_path: Path) -> None:
    vault_root = fake_vault(tmp_path, "import time\ntime.sleep(30)\n")

    outcome = VaultPublishCli().publish_draft(vault_root, draft_file(tmp_path), timeout_s=0.5)

    assert outcome.status == "error"
    assert any("Vault git status" in message for message in outcome.messages)


def test_vault_without_tools_is_an_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    outcome = VaultPublishCli().publish_draft(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"
    assert any("no publish-draft" in message for message in outcome.messages)


def test_long_output_is_cut_to_the_last_lines(tmp_path: Path) -> None:
    script = 'for i in range(100):\n    print(f"line {i}")\nprint("Applied draft: wiki/systems/b.md")\n'
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish_draft(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.written_paths == ("wiki/systems/b.md",)
    assert len(outcome.messages) <= 20
    assert outcome.messages[-1] == "Applied draft: wiki/systems/b.md"


def _vault_template() -> Path | None:
    configured = os.environ.get(VAULT_TEMPLATE_ENV)
    candidate = Path(configured) if configured else Path.home() / "workspace" / "vault-builder"
    if (candidate / CLI_RELATIVE_PATH).is_file() and (candidate / "wiki" / "index.md").is_file():
        return candidate
    return None


@pytest.fixture
def copied_vault(tmp_path: Path) -> Path:
    template = _vault_template()
    if template is None:
        pytest.skip(f"Vault tools are not available; set {VAULT_TEMPLATE_ENV} to a Vault template to run A-14.")
    target = tmp_path / "copied-vault"
    shutil.copytree(
        template,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "builder_tests", "tests", ".venv"),
    )
    return target


class OneVaultMap:
    def __init__(self, vault: MappedVault) -> None:
        self._vault = vault

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return (self._vault,)

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        return MappedProjectMatch("project", "root", (self._vault,))

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return (self._vault,)


def test_a14_remember_publishes_one_decision_page_in_a_copied_vault(copied_vault: Path, tmp_path: Path) -> None:
    service = MemoryWriteService(
        vault_map=OneVaultMap(MappedVault(name="copy", path=copied_vault, role="project")),
        publisher=VaultPublishCli(python_executable=sys.executable),
    )

    result = service.remember(
        RememberRequest(
            title="Keep the vault-graph index in SQLite",
            kind="decision",
            body="The local index stays in SQLite files under Graph Home.",
            evidence=("User statement in the 2026-10-30 session.",),
            vault="copy",
        )
    )

    assert result.status == "published", result.messages
    assert result.written_paths == ("wiki/decisions/keep-the-vault-graph-index-in-sqlite.md",)
    assert (copied_vault / result.written_paths[0]).is_file()


def test_a14_draft_without_a_required_field_is_rejected_and_leaves_the_copy_unchanged(
    copied_vault: Path, tmp_path: Path
) -> None:
    draft = build_draft(
        RememberRequest(title="Missing owner", kind="decision", body="Body.", evidence=("User statement.",)),
        today=date.today(),
    )
    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    del frontmatter["owner"]
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    before = file_bytes(copied_vault)

    outcome = VaultPublishCli().publish_draft(copied_vault, draft_path, timeout_s=120)

    assert outcome.status == "rejected", outcome.messages
    assert file_bytes(copied_vault) == before
