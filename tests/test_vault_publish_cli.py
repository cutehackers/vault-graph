"""The Vault CLI adapter reads only the 계약1 and 계약4 JSON (spec 2026-11-02 V3 어댑터, 6절).

``publish`` runs ``publish-draft --json`` (계약1). ``propose`` runs ``review propose --json`` (계약4).

The optional A-14 run on a copied Vault runs only when Vault tools are available. It copies them into
a temporary directory and never touches the user's real Vault.
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
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
from vault_graph.interface.composition.adapters.vault_publish_cli import (
    CLI_RELATIVE_PATH,
    MAX_MESSAGE_LINES,
    VaultPublishCli,
)
from vault_graph.operation.memory.memory_drafts import build_remember_draft
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


def json_script(result: dict[str, object], *, exit_code: int, stderr: str = "") -> str:
    return (
        "import json, os, sys\n"
        f"sys.stderr.write({stderr!r})\n"
        f"result = json.loads({json.dumps(result)!r})\n"
        'result["messages"] = result["messages"] + ["argv=" + "|".join(sys.argv[1:]), "cwd=" + os.getcwd(),'
        ' "flags=" + str(sys.flags.isolated) + str(sys.flags.dont_write_bytecode)]\n'
        "print(json.dumps(result))\n"
        f"sys.exit({exit_code})\n"
    )


def contract_result(status: str, reason: str | None, written: list[str], messages: list[str]) -> dict[str, object]:
    return {
        "format": "vault-publish-result/v1",
        "draft_version": 1,
        "status": status,
        "reason": reason,
        "written_paths": written,
        "messages": messages,
    }


def test_runs_publish_draft_json_from_the_vault_root_and_reads_written_paths(tmp_path: Path) -> None:
    script = json_script(
        contract_result("published", None, ["wiki/decisions/a.md", "wiki/index.md"], []),
        exit_code=0,
        stderr="Applied draft: wiki/decisions/a.md\n",
    )
    vault_root = fake_vault(tmp_path, script)
    draft = draft_file(tmp_path)

    outcome = VaultPublishCli().publish(vault_root, draft, timeout_s=30)

    assert outcome.status == "published"
    assert outcome.reason is None
    assert outcome.written_paths == ("wiki/decisions/a.md", "wiki/index.md")
    assert f"argv=publish-draft|{draft}|--json" in outcome.messages
    assert f"cwd={vault_root.resolve()}" in outcome.messages
    assert "flags=11" in outcome.messages
    assert not any("Applied draft" in message for message in outcome.messages)


def test_human_locked_is_rejected_with_the_vault_message(tmp_path: Path) -> None:
    lock_message = "Target page is human-locked: wiki/decisions/a.md"
    script = json_script(contract_result("rejected", "human-locked", [], [lock_message]), exit_code=1)
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.reason == "human-locked"
    assert outcome.written_paths == ()
    assert lock_message in outcome.messages
    assert any("human-locked" in message for message in outcome.messages)


def test_lint_dirty_before_asks_to_fix_the_vault_lint_first(tmp_path: Path) -> None:
    script = json_script(
        contract_result("rejected", "lint-dirty-before", [], ["[error] broken-link wiki/a.md:3 - x"]), exit_code=1
    )
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "rejected"
    assert "[error] broken-link wiki/a.md:3 - x" in outcome.messages
    assert any("Fix the Vault lint first" in message for message in outcome.messages)


def test_vault_tools_without_json_flag_ask_for_contract_4_migration(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        'sys.stderr.write("usage: cli.py [-h]\\ncli.py: error: unrecognized arguments: --json\\n")\n'
        "sys.exit(2)\n"
    )
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"
    assert any("contract 4" in message and "Migrate" in message for message in outcome.messages)


def test_output_that_is_not_json_is_an_error_with_the_last_lines(tmp_path: Path) -> None:
    script = 'for i in range(100):\n    print(f"line {i}")\n'
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"
    assert outcome.written_paths == ()
    assert "line 99" in outcome.messages
    assert "line 70" not in outcome.messages
    assert len([message for message in outcome.messages if message.startswith("line ")]) == MAX_MESSAGE_LINES == 20


@pytest.mark.parametrize(
    "result",
    [
        {**contract_result("published", None, [], []), "format": "vault-publish-result/v2"},
        {**contract_result("published", None, [], []), "status": "maybe"},
        ["not", "an", "object"],
    ],
    ids=["format", "status", "shape"],
)
def test_json_outside_contract_1_is_an_error(tmp_path: Path, result: object) -> None:
    vault_root = fake_vault(tmp_path, f"import json\nprint(json.dumps({result!r}))\n")

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"


def test_timeout_stops_the_process_and_is_an_error(tmp_path: Path) -> None:
    vault_root = fake_vault(tmp_path, "import time\ntime.sleep(30)\n")

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=0.5)

    assert outcome.status == "error"
    assert any("did not finish in 0.5 seconds" in message for message in outcome.messages)
    assert any("Vault git status" in message for message in outcome.messages)


def test_vault_without_tools_is_an_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    outcome = VaultPublishCli().publish(vault_root, draft_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"
    assert any("no publish-draft" in message for message in outcome.messages)


# 계약4: review propose --json


def review_result(status: str, review_path: str | None, messages: list[str]) -> dict[str, object]:
    return {
        "format": "vault-review-result/v1",
        "status": status,
        "review_id": None if review_path is None else "2026-11-02-memory-1a2b3c4d",
        "review_path": review_path,
        "draft_path": None if review_path is None else "scratch/review/2026-11-02-memory-1a2b3c4d.draft.json",
        "target_path": None if review_path is None else "wiki/decisions/a.md",
        "messages": messages,
    }


def test_propose_runs_review_propose_json_from_the_vault_root_and_reads_review_path(tmp_path: Path) -> None:
    review_path = "scratch/review/2026-11-02-memory-1a2b3c4d.md"
    script = json_script(review_result("proposed", review_path, []), exit_code=0, stderr="Review item created\n")
    vault_root = fake_vault(tmp_path, script)
    draft = draft_file(tmp_path)

    outcome = VaultPublishCli().propose(vault_root, draft, summary="Add memory: A", timeout_s=30)

    assert outcome.status == "proposed"
    assert outcome.review_path == review_path
    assert outcome.written_paths == ()
    assert f"argv=review|propose|--draft|{draft}|--summary|Add memory: A|--json" in outcome.messages
    assert f"cwd={vault_root.resolve()}" in outcome.messages
    assert "flags=11" in outcome.messages
    assert not any("Review item created" in message for message in outcome.messages)


def test_propose_exit_1_is_rejected_with_the_vault_messages(tmp_path: Path) -> None:
    refusal = "Memory proposal already exists: scratch/review/2026-11-02-memory-1a2b3c4d.md"
    vault_root = fake_vault(tmp_path, json_script(review_result("rejected", None, [refusal]), exit_code=1))

    outcome = VaultPublishCli().propose(vault_root, draft_file(tmp_path), summary="S", timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.review_path is None
    assert refusal in outcome.messages


@pytest.mark.parametrize(
    "stderr",
    [
        "cli.py: error: unrecognized arguments: --json\n",
        "cli.py review: error: argument review_command: invalid choice: 'propose'\n",
    ],
    ids=["no-json-flag", "no-propose-command"],
)
def test_propose_exit_2_asks_for_vault_migration(tmp_path: Path, stderr: str) -> None:
    vault_root = fake_vault(tmp_path, f"import sys\nsys.stderr.write({stderr!r})\nsys.exit(2)\n")

    outcome = VaultPublishCli().propose(vault_root, draft_file(tmp_path), summary="S", timeout_s=30)

    assert outcome.status == "error"
    assert any("review propose" in message and "Migrate" in message for message in outcome.messages)


@pytest.mark.parametrize(
    "result",
    [
        {**review_result("proposed", "scratch/review/a.md", []), "format": "vault-review-result/v2"},
        {**review_result("proposed", "scratch/review/a.md", []), "status": "resolved"},
        review_result("proposed", None, []),
        {**review_result("proposed", "scratch/review/a.md", []), "messages": "one"},
        ["not", "an", "object"],
    ],
    ids=["format", "status", "no-review-path", "messages", "shape"],
)
def test_propose_json_outside_contract_4_is_an_error(tmp_path: Path, result: object) -> None:
    vault_root = fake_vault(tmp_path, f"import json\nprint(json.dumps({result!r}))\n")

    outcome = VaultPublishCli().propose(vault_root, draft_file(tmp_path), summary="S", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.review_path is None


def test_propose_text_output_is_an_error_with_the_last_lines(tmp_path: Path) -> None:
    vault_root = fake_vault(tmp_path, 'print("Review item created: scratch/review/a.md")\n')

    outcome = VaultPublishCli().propose(vault_root, draft_file(tmp_path), summary="S", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.review_path is None
    assert "Review item created: scratch/review/a.md" in outcome.messages


def test_propose_timeout_and_missing_tools_are_errors(tmp_path: Path) -> None:
    slow = fake_vault(tmp_path, "import time\ntime.sleep(30)\n")
    empty = tmp_path / "empty-vault"
    empty.mkdir()

    timed_out = VaultPublishCli().propose(slow, draft_file(tmp_path), summary="S", timeout_s=0.5)
    missing = VaultPublishCli().propose(empty, tmp_path / "drafts" / "draft.json", summary="S", timeout_s=30)

    assert timed_out.status == "error"
    assert any("review propose did not finish in 0.5 seconds" in message for message in timed_out.messages)
    assert missing.status == "error"
    assert any(str(CLI_RELATIVE_PATH) in message for message in missing.messages)


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
        writer=VaultPublishCli(python_executable=sys.executable),
        page_reader=VaultPageFileReader(),
        drafts=TemporaryDraftFiles(),
    )

    result = service.remember(
        RememberRequest(
            title="Keep the vault-graph index in SQLite",
            kind="decision",
            body="The local index stays in SQLite files under Graph Home.",
            evidence=("User statement in the 2026-10-30 session.",),
            basis="stated",
            vault="copy",
        )
    )

    assert result.status == "published", result.messages
    assert result.written_paths[0] == "wiki/decisions/keep-the-vault-graph-index-in-sqlite.md"
    assert (copied_vault / result.written_paths[0]).is_file()


def test_a14_draft_without_a_required_field_is_rejected_and_leaves_the_copy_unchanged(
    copied_vault: Path, tmp_path: Path
) -> None:
    draft = build_remember_draft(
        RememberRequest(
            title="Missing owner", kind="decision", body="Body.", evidence=("User statement.",), basis="stated"
        ),
        today=date.today(),
    )
    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    del frontmatter["owner"]
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    before = file_bytes(copied_vault)

    outcome = VaultPublishCli().publish(copied_vault, draft_path, timeout_s=120)

    assert outcome.status == "rejected", outcome.messages
    assert outcome.reason is not None
    assert file_bytes(copied_vault) == before


def test_a14_inferred_remember_is_proposed_in_a_copied_vault_and_wiki_is_unchanged(copied_vault: Path) -> None:
    service = MemoryWriteService(
        vault_map=OneVaultMap(MappedVault(name="copy", path=copied_vault, role="project")),
        writer=VaultPublishCli(python_executable=sys.executable),
        page_reader=VaultPageFileReader(),
        drafts=TemporaryDraftFiles(),
    )
    wiki_before = file_bytes(copied_vault / "wiki")

    result = service.remember(
        RememberRequest(
            title="The index probably stays in SQLite",
            kind="decision",
            body="The agent inferred that the local index stays in SQLite files.",
            evidence=("Agent inference from the 2026-11-02 session.",),
            basis="inferred",
            vault="copy",
        )
    )

    assert result.status == "proposed", result.messages
    assert result.review_path is not None
    assert result.review_path.startswith("scratch/review/") and result.review_path.endswith(".md")
    assert (copied_vault / result.review_path).is_file()
    assert (copied_vault / result.review_path.removesuffix(".md")).with_suffix(".draft.json").is_file()
    assert any(f"review resolve {result.review_path} --status accepted" in message for message in result.messages)
    assert result.written_paths == ()
    assert file_bytes(copied_vault / "wiki") == wiki_before
