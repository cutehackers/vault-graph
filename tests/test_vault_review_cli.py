"""The review resolve adapter trusts only the Vault's contract JSON (spec 2026-11-20-vg-review-accept D9, I5, A3).

A stand-in ``tools/wiki/cli.py`` under ``tmp_path`` plays the Vault tool. No real Vault is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.interface.composition.adapters.vault_publish_cli import CLI_RELATIVE_PATH, MAX_MESSAGE_LINES
from vault_graph.interface.composition.adapters.vault_review_cli import (
    RESOLVE_MIGRATE_MESSAGE,
    TARGET_CHANGED_GUIDANCE,
    TIMEOUT_GUIDANCE,
    VaultReviewCli,
)
from vault_graph.operation.memory.memory_write_service import PUBLISH_TIMEOUT_SECONDS

REVIEW_PATH = "scratch/review/2026-11-20-memory-1a2b3c4d.md"


def fake_vault(tmp_path: Path, script: str) -> Path:
    vault_root = tmp_path / "vault"
    cli = vault_root / CLI_RELATIVE_PATH
    cli.parent.mkdir(parents=True)
    cli.write_text(script, encoding="utf-8")
    return vault_root


def json_script(result: dict[str, object], *, exit_code: int, stderr: str = "") -> str:
    return (
        "import json, os, sys\n"
        f"sys.stderr.write({stderr!r})\n"
        f"result = json.loads({json.dumps(result)!r})\n"
        'result["messages"] = result["messages"] + ["argv=" + "|".join(sys.argv[1:]), "cwd=" + os.getcwd(),'
        ' "flags=" + str(sys.flags.isolated) + str(sys.flags.dont_write_bytecode)]\n'
        "print(json.dumps(result, ensure_ascii=False))\n"
        f"sys.exit({exit_code})\n"
    )


def plain_script(result: object, *, exit_code: int, stderr: str = "") -> str:
    return (
        "import json, sys\n"
        f"sys.stderr.write({stderr!r})\n"
        f"print(json.dumps(json.loads({json.dumps(result)!r}), ensure_ascii=False))\n"
        f"sys.exit({exit_code})\n"
    )


def resolve_result(
    status: str, reason: str | None, written: list[str], messages: list[str], *, review_status: str = "pending"
) -> dict[str, object]:
    return {
        "format": "vault-review-result/v1",
        "status": status,
        "review_status": review_status,
        "reason": reason,
        "review_id": "2026-11-20-memory-1a2b3c4d",
        "review_path": REVIEW_PATH,
        "draft_path": None,
        "target_path": "wiki/decisions/a.md",
        "written_paths": written,
        "messages": messages,
    }


def test_accept_runs_review_resolve_json_from_the_vault_root_and_reads_written_paths(tmp_path: Path) -> None:
    script = json_script(
        resolve_result("resolved", None, ["wiki/decisions/a.md", "wiki/log.md"], [], review_status="accepted"),
        exit_code=0,
        stderr="Applied draft: wiki/decisions/a.md\n",
    )
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="사람이 확인함")

    assert outcome.status == "resolved"
    assert outcome.reason is None
    assert outcome.written_paths == ("wiki/decisions/a.md", "wiki/log.md")
    assert outcome.guidance == ()
    assert f"argv=review|resolve|{REVIEW_PATH}|--status|accepted|--resolution|사람이 확인함|--json" in outcome.messages
    assert f"cwd={vault_root.resolve()}" in outcome.messages
    assert "flags=11" in outcome.messages
    assert not any("Applied draft" in message for message in outcome.messages)


def test_reject_passes_the_status_and_the_reason_text(tmp_path: Path) -> None:
    script = json_script(resolve_result("resolved", None, [], [], review_status="rejected"), exit_code=0)
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="rejected", resolution="틀린 추론", timeout_s=30)

    assert outcome.status == "resolved"
    assert outcome.written_paths == ()
    assert f"argv=review|resolve|{REVIEW_PATH}|--status|rejected|--resolution|틀린 추론|--json" in outcome.messages


def test_the_default_time_limit_is_the_publish_time_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    seen: dict[str, object] = {}
    real_run = subprocess.run

    def recording_run(*args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return real_run(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", recording_run)
    vault_root = fake_vault(tmp_path, json_script(resolve_result("resolved", None, [], []), exit_code=0))

    VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="rejected", resolution="r")

    assert seen["timeout"] == PUBLISH_TIMEOUT_SECONDS == 120.0
    assert seen["cwd"] == vault_root


def test_target_changed_is_a_failure_with_the_vault_message_and_reject_then_propose_guidance(tmp_path: Path) -> None:
    refusal = "Target page changed since the proposal: wiki/decisions/a.md"
    script = plain_script(resolve_result("rejected", "target-changed", [], [refusal]), exit_code=1)
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.reason == "target-changed"
    assert outcome.written_paths == ()
    assert outcome.messages == (refusal,)
    assert outcome.guidance == (TARGET_CHANGED_GUIDANCE,)
    assert "Reject" in TARGET_CHANGED_GUIDANCE and "propose it again" in TARGET_CHANGED_GUIDANCE


def test_a_publish_refusal_is_a_failure_with_the_vault_messages_unchanged(tmp_path: Path) -> None:
    lint_line = "[error] broken-link wiki/decisions/a.md:3 - 깨진 링크"
    script = plain_script(resolve_result("rejected", "lint-failed", [], [lint_line]), exit_code=1)
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.reason == "lint-failed"
    assert outcome.messages == (lint_line,)
    assert outcome.guidance == ()


def test_a_lint_gated_refusal_without_messages_shows_the_vault_error_output(tmp_path: Path) -> None:
    abort = "Review resolution aborted: wiki lint must be clean before resolving a review item."
    script = plain_script(
        resolve_result("rejected", "review-invalid", [], []),
        exit_code=1,
        stderr=f"[error] broken-link wiki/a.md:3 - x\n{abort}\n",
    )
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="rejected", resolution="no", timeout_s=30)

    assert outcome.status == "rejected"
    assert outcome.reason == "review-invalid"
    assert outcome.messages == ("[error] broken-link wiki/a.md:3 - x", abort)


def test_exit_code_2_asks_for_contract_4_migration(tmp_path: Path) -> None:
    script = (
        "import sys\n"
        'sys.stderr.write("usage: cli.py [-h]\\ncli.py: error: unrecognized arguments: --json\\n")\n'
        "sys.exit(2)\n"
    )
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.written_paths == ()
    assert outcome.guidance == (RESOLVE_MIGRATE_MESSAGE,)
    assert "contract 4" in RESOLVE_MIGRATE_MESSAGE and "Migrate" in RESOLVE_MIGRATE_MESSAGE
    assert any("unrecognized arguments: --json" in message for message in outcome.messages)


def test_output_that_is_not_json_is_an_error_with_the_last_lines(tmp_path: Path) -> None:
    script = 'for i in range(100):\n    print(f"line {i}")\nprint("Review item resolved: x")\n'
    vault_root = fake_vault(tmp_path, script)

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.written_paths == ()
    assert "without a vault-review-result/v1 JSON object" in outcome.messages[0]
    assert "line 99" in outcome.messages
    assert "line 70" not in outcome.messages
    assert len(outcome.messages) == MAX_MESSAGE_LINES + 1


@pytest.mark.parametrize(
    "result",
    [
        {**resolve_result("resolved", None, ["wiki/a.md"], []), "format": "vault-publish-result/v1"},
        {**resolve_result("resolved", None, ["wiki/a.md"], []), "status": "proposed"},
        {**resolve_result("resolved", None, ["wiki/a.md"], []), "status": "accepted"},
        {**resolve_result("resolved", None, [], []), "written_paths": "wiki/a.md"},
        {**resolve_result("resolved", None, ["wiki/a.md"], []), "messages": None},
        {**resolve_result("resolved", None, ["wiki/a.md"], []), "reason": 3},
        ["not", "an", "object"],
    ],
    ids=["format", "propose-status", "review-status-word", "written-paths", "messages", "reason", "shape"],
)
def test_json_outside_the_resolve_contract_is_an_error_and_never_resolved(tmp_path: Path, result: object) -> None:
    vault_root = fake_vault(tmp_path, plain_script(result, exit_code=0))

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.written_paths == ()


def test_timeout_stops_the_process_and_says_the_result_is_unknown(tmp_path: Path) -> None:
    vault_root = fake_vault(tmp_path, "import time\ntime.sleep(30)\n")

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=0.5)

    assert outcome.status == "error"
    assert outcome.written_paths == ()
    assert any("did not finish in 0.5 seconds" in message for message in outcome.messages)
    assert any("result is unknown" in message for message in outcome.messages)
    assert outcome.guidance == (TIMEOUT_GUIDANCE,)
    assert "vg review list" in TIMEOUT_GUIDANCE and "git status" in TIMEOUT_GUIDANCE


def test_vault_without_tools_is_an_error_that_names_the_missing_file(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    outcome = VaultReviewCli().resolve(vault_root, REVIEW_PATH, status="accepted", resolution="ok", timeout_s=30)

    assert outcome.status == "error"
    assert outcome.messages == (f"This Vault has no review resolve: {CLI_RELATIVE_PATH} is missing.",)
    assert list(vault_root.iterdir()) == []
