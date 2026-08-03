from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.harness.harness_guidance import (
    HARNESS_GUIDANCE_END_MARKER,
    HARNESS_GUIDANCE_START_MARKER,
    HarnessGuidanceError,
    HarnessGuidanceRequest,
    HarnessGuidanceService,
)


def _service(tmp_path: Path) -> HarnessGuidanceService:
    return HarnessGuidanceService(vault_roots=(tmp_path / "vault",))


def test_install_appends_static_marker_block_and_preserves_existing_content(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    instruction = project / "AGENTS.md"
    instruction.write_text("# Existing rules\n\nKeep this line.\n", encoding="utf-8")

    report = _service(tmp_path).install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    content = instruction.read_text(encoding="utf-8")
    assert report.changed is True
    assert report.backup_path == project / "AGENTS.md.install.bak"
    assert report.backup_path.read_text(encoding="utf-8") == "# Existing rules\n\nKeep this line.\n"
    assert content.startswith("# Existing rules\n\nKeep this line.\n")
    assert content.count(HARNESS_GUIDANCE_START_MARKER) == 1
    assert content.count(HARNESS_GUIDANCE_END_MARKER) == 1
    assert "Call `explore_project` first" in content
    assert "vg code" in content
    assert "durable knowledge" in content


def test_install_is_idempotent_and_does_not_create_a_second_backup(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = _service(tmp_path)
    request = HarnessGuidanceRequest(target=project, file_name="CLAUDE.md")

    service.install(request)
    report = service.install(request)

    assert report.changed is False
    assert report.backup_path is None
    assert (project / "CLAUDE.md").read_text(encoding="utf-8").count(HARNESS_GUIDANCE_START_MARKER) == 1


def test_remove_restores_only_marker_block_and_preserves_user_edits(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = _service(tmp_path)
    request = HarnessGuidanceRequest(target=project, file_name="AGENTS.md")
    service.install(request)
    instruction = project / "AGENTS.md"
    instruction.write_text(instruction.read_text(encoding="utf-8") + "\nUser rule after install.\n", encoding="utf-8")

    report = service.remove(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    content = instruction.read_text(encoding="utf-8")
    assert report.changed is True
    assert report.backup_path == project / "AGENTS.md.remove.bak"
    assert HARNESS_GUIDANCE_START_MARKER not in content
    assert HARNESS_GUIDANCE_END_MARKER not in content
    assert "User rule after install." in content


def test_default_install_then_default_remove_is_reversible(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    instruction = project / "AGENTS.md"
    instruction.write_text("# Existing rules\n", encoding="utf-8")
    service = _service(tmp_path)

    installed = service.install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))
    removed = service.remove(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    assert installed.backup_path == project / "AGENTS.md.install.bak"
    assert removed.backup_path == project / "AGENTS.md.remove.bak"
    assert instruction.read_text(encoding="utf-8") == "# Existing rules\n"


def test_install_and_remove_preserve_trailing_whitespace_and_blank_lines(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    instruction = project / "AGENTS.md"
    original = "# Existing rules  \n\n\n"
    instruction.write_text(original, encoding="utf-8")
    service = _service(tmp_path)

    service.install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))
    service.remove(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    assert instruction.read_text(encoding="utf-8") == original


def test_install_rejects_existing_backup_and_tampered_marker(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    instruction = project / "AGENTS.md"
    instruction.write_text(HARNESS_GUIDANCE_START_MARKER + "\n", encoding="utf-8")

    with pytest.raises(HarnessGuidanceError, match="harness_guidance_marker_tampered"):
        _service(tmp_path).install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    instruction.write_text("existing\n", encoding="utf-8")
    (project / "AGENTS.md.install.bak").write_text("backup\n", encoding="utf-8")
    with pytest.raises(HarnessGuidanceError, match="harness_guidance_backup_exists"):
        _service(tmp_path).install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))


def test_remove_rejects_missing_or_tampered_marker(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    instruction = project / "CLAUDE.md"
    instruction.write_text("plain user content\n", encoding="utf-8")

    with pytest.raises(HarnessGuidanceError, match="harness_guidance_marker_missing"):
        _service(tmp_path).remove(HarnessGuidanceRequest(target=project, file_name="CLAUDE.md"))


def test_install_rejects_broken_instruction_symlink(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").symlink_to(project / "missing-target")

    with pytest.raises(HarnessGuidanceError, match="harness_guidance_symlink_not_allowed"):
        _service(tmp_path).install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))


def test_remove_rejects_explicit_backup_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    service = _service(tmp_path)
    service.install(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    with pytest.raises(HarnessGuidanceError, match="harness_guidance_remove_backup_not_supported"):
        service.remove(
            HarnessGuidanceRequest(target=project, file_name="AGENTS.md", backup_path=project / "custom.bak")
        )
