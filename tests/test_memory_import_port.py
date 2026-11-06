"""import_auto_memory: keep a copy of one Claude Code auto-memory note through Vault ``import-source``.

Source: spec 2026-11-05 §4.4.5 (path 4), §6 ("import-source를 모르는 Vault"), A-24 (vg side), A-31.
The adapter runs the Vault command and reads only its JSON. vault-graph never copies the note itself.
Fake Vault CLIs stand in for the real command until the E2E check (#37).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.test_memory_write_service import FakeVaultMap, RecordingWriter, make_vault
from tests.test_read_only_boundary import file_bytes
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.interface.composition.adapters.vault_import_cli import (
    CLAUDE_MEMORY_IMPORT_DIR,
    UPDATE_VAULT_TOOLS_MESSAGE,
    VaultImportCli,
)
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import ImportRequest, validate_import
from vault_graph.operation.memory.memory_write_service import MemoryWriteService
from vault_graph.project.context.project_binding_reader import MappedVault

IMPORTED = {
    "status": "imported",
    "raw_path": "raw/imports/claude-memory/feedback--1a2b3c4d.md",
    "source_page": "wiki/sources/feedback-1a2b3c4d.md",
    "sha256": "1a2b3c4d" + "0" * 56,
    "created": ["raw/imports/claude-memory/feedback--1a2b3c4d.md", "wiki/sources/feedback-1a2b3c4d.md"],
}

# A Vault CLI that knows import-source. It refuses any arguments other than the expected ones.
NEW_CLI = """
import json, sys
expected = json.loads({expected!r})
if sys.argv[1:] != expected:
    print("unexpected arguments: " + repr(sys.argv[1:]), file=sys.stderr)
    sys.exit(3)
print({stdout!r})
sys.exit({code})
"""

# A Vault CLI from before request S8: argparse does not know import-source.
OLD_CLI = """
import argparse
parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("publish-draft")
parser.parse_args()
"""


def write_cli(vault_root: Path, source: str) -> None:
    cli = vault_root / "tools" / "wiki" / "cli.py"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text(source, encoding="utf-8")


def note_file(tmp_path: Path) -> Path:
    folder = tmp_path / "claude" / "projects" / "p" / "memory"
    folder.mkdir(parents=True)
    note = folder / "feedback.md"
    note.write_text("Use uv, not pip.\n", encoding="utf-8")
    return note


def new_cli(vault_root: Path, note: Path, stdout: str, code: int = 0) -> None:
    expected = json.dumps(["import-source", str(note), "--into", CLAUDE_MEMORY_IMPORT_DIR, "--json"])
    write_cli(vault_root, NEW_CLI.format(expected=expected, stdout=stdout, code=code))


# Adapter


def test_adapter_runs_import_source_into_the_claude_memory_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    new_cli(vault, note, json.dumps(IMPORTED))

    outcome = VaultImportCli(python_executable=sys.executable).import_source(vault, note, timeout_s=30)

    assert CLAUDE_MEMORY_IMPORT_DIR == "raw/imports/claude-memory/"
    assert outcome.status == "published"
    assert outcome.raw_path == IMPORTED["raw_path"]
    assert outcome.source_page == IMPORTED["source_page"]
    assert outcome.written_paths == tuple(IMPORTED["created"])


def test_adapter_reports_an_existing_copy_with_nothing_written(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    new_cli(vault, note, json.dumps({**IMPORTED, "status": "exists", "created": []}))

    outcome = VaultImportCli().import_source(vault, note, timeout_s=30)

    assert outcome.status == "published"
    assert outcome.raw_path == IMPORTED["raw_path"]
    assert outcome.written_paths == ()
    assert any("already" in message.lower() for message in outcome.messages)


def test_adapter_returns_the_vault_error_message_as_rejected(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    message = "File does not exist or is not a regular file: feedback.md."
    new_cli(vault, note, json.dumps({"status": "error", "message": message}), code=1)

    outcome = VaultImportCli().import_source(vault, note, timeout_s=30)

    assert outcome.status == "rejected"
    assert message in outcome.messages
    assert outcome.raw_path is None


def test_adapter_tells_to_update_the_vault_tools_when_import_source_is_unknown(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    write_cli(vault, OLD_CLI)

    outcome = VaultImportCli().import_source(vault, note, timeout_s=30)

    assert outcome.status == "error"
    assert outcome.messages[0] == UPDATE_VAULT_TOOLS_MESSAGE
    assert "Update the Vault tools" in UPDATE_VAULT_TOOLS_MESSAGE


def test_adapter_reports_a_vault_without_tools(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    outcome = VaultImportCli().import_source(vault, note_file(tmp_path), timeout_s=30)

    assert outcome.status == "error"


def test_adapter_reports_output_that_is_not_the_import_json(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    new_cli(vault, note, "Imported: something")

    outcome = VaultImportCli().import_source(vault, note, timeout_s=30)

    assert outcome.status == "error"


def test_adapter_leaves_the_note_unchanged(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = note_file(tmp_path)
    new_cli(vault, note, json.dumps(IMPORTED))
    before = file_bytes(note.parent)
    mtime = note.stat().st_mtime_ns

    VaultImportCli().import_source(vault, note, timeout_s=30)

    assert file_bytes(note.parent) == before
    assert note.stat().st_mtime_ns == mtime


# Service


class FakeImporter:
    def __init__(self, outcome: WriteOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Path, Path, float]] = []

    def import_source(self, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
        self.calls.append((vault_root, note_path, timeout_s))
        return self.outcome


class NoPages:
    def read(self, vault_root: Path, path: str) -> None:
        return None


def import_service(tmp_path: Path, importer: object | None, vaults: tuple[MappedVault, ...]) -> MemoryWriteService:
    temp_root = tmp_path / "os-temp"
    temp_root.mkdir(exist_ok=True)
    return MemoryWriteService(
        vault_map=FakeVaultMap(vaults, {}),
        writer=RecordingWriter(),
        page_reader=NoPages(),
        drafts=TemporaryDraftFiles(temp_root=temp_root),
        importer=importer,  # type: ignore[arg-type]
    )


def test_service_imports_into_the_chosen_vault_and_returns_the_copy_path(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    note = note_file(tmp_path)
    importer = FakeImporter(
        WriteOutcome(
            "published",
            written_paths=tuple(IMPORTED["created"]),
            raw_path=str(IMPORTED["raw_path"]),
            source_page=str(IMPORTED["source_page"]),
        )
    )

    result = import_service(tmp_path, importer, (vault,)).import_auto_memory(
        ImportRequest(note=str(note), vault="main")
    )

    assert result.status == "published"
    assert result.vault == "main"
    assert result.raw_path == IMPORTED["raw_path"]
    assert result.source_page == IMPORTED["source_page"]
    assert [(root, path) for root, path, _ in importer.calls] == [(vault.path, note)]


def test_service_passes_the_update_message_on_for_an_old_vault(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    importer = FakeImporter(WriteOutcome("error", messages=(UPDATE_VAULT_TOOLS_MESSAGE,)))

    result = import_service(tmp_path, importer, (vault,)).import_auto_memory(
        ImportRequest(note=str(note_file(tmp_path)), vault="main")
    )

    assert result.status == "error"
    assert UPDATE_VAULT_TOOLS_MESSAGE in result.messages


def test_service_with_the_real_adapter_and_an_old_vault_returns_error_and_update_message(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    write_cli(vault.path, OLD_CLI)

    result = import_service(tmp_path, VaultImportCli(), (vault,)).import_auto_memory(
        ImportRequest(note=str(note_file(tmp_path)), vault="main")
    )

    assert result.status == "error"
    assert any("Update the Vault tools" in message for message in result.messages)


def test_service_turns_an_importer_exception_into_error(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")

    class Raising:
        def import_source(self, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
            raise RuntimeError("boom")

    result = import_service(tmp_path, Raising(), (vault,)).import_auto_memory(
        ImportRequest(note=str(note_file(tmp_path)), vault="main")
    )

    assert result.status == "error"


def test_service_without_an_importer_returns_error(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")

    result = import_service(tmp_path, None, (vault,)).import_auto_memory(
        ImportRequest(note=str(note_file(tmp_path)), vault="main")
    )

    assert result.status == "error"


@pytest.mark.parametrize(
    ("note", "field"),
    [("", "note"), ("relative/feedback.md", "note")],
)
def test_import_request_needs_an_absolute_note_path(note: str, field: str) -> None:
    problems = validate_import(ImportRequest(note=note))

    assert any(problem.startswith(field) for problem in problems)


def test_invalid_import_request_does_not_call_the_vault(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    importer = FakeImporter(WriteOutcome("published"))

    result = import_service(tmp_path, importer, (vault,)).import_auto_memory(ImportRequest(note="relative.md"))

    assert result.status == "rejected"
    assert importer.calls == []
