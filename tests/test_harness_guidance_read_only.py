from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.harness.harness_guidance import HarnessGuidanceError, HarnessGuidanceRequest, HarnessGuidanceService


def test_preview_does_not_write_instruction_or_backup(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    report = HarnessGuidanceService().preview(HarnessGuidanceRequest(target=project, file_name="AGENTS.md"))

    assert report.changed is True
    assert report.preview is True
    assert not (project / "AGENTS.md").exists()
    assert not (project / "AGENTS.md.bak").exists()


def test_guidance_rejects_targets_inside_vault_and_symlink_paths(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    service = HarnessGuidanceService(vault_roots=(vault,))

    with pytest.raises(HarnessGuidanceError, match="harness_guidance_target_inside_vault"):
        service.install(HarnessGuidanceRequest(target=vault, file_name="AGENTS.md"))
    with pytest.raises(HarnessGuidanceError, match="harness_guidance_symlink_not_allowed"):
        service.install(HarnessGuidanceRequest(target=link, file_name="AGENTS.md"))


def test_default_harness_service_construction_performs_no_writes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    HarnessGuidanceService(vault_roots=())

    assert list(project.iterdir()) == []
