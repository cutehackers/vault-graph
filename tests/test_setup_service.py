from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.app.index_service import IndexRunReport
from vault_graph.app.setup_service import SetupRequest, SetupService
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.ingestion.vault_catalog import QueryScope


class RecordingIndexService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_apply(self, **kwargs: object) -> IndexRunReport:
        self.calls.append(kwargs)
        return IndexRunReport(
            metadata=MetadataRevisionPlan(
                index_revision="metadata-1",
                mode="incremental",
                vault_ids=("main",),
                changed_paths=(),
                unchanged_paths=(),
                deleted_paths=(),
                warnings=(),
            ),
            vector=None,
            graph=None,
        )


class RecordingBundle:
    def __init__(self, index_service: RecordingIndexService) -> None:
        self.index_service = index_service
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RecordingIndexFactory:
    def __init__(self) -> None:
        self.index_service = RecordingIndexService()
        self.bundles: list[RecordingBundle] = []
        self.calls: list[dict[str, object]] = []

    def open(self, **kwargs: object) -> RecordingBundle:
        self.calls.append(kwargs)
        bundle = RecordingBundle(self.index_service)
        self.bundles.append(bundle)
        return bundle


def make_vault(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    return vault_root


def test_setup_dry_run_writes_nothing(tmp_path: Path) -> None:
    factory = RecordingIndexFactory()

    report = SetupService(index_factory=cast(Any, factory)).setup(
        SetupRequest(
            vault_path=make_vault(tmp_path),
            state_path=tmp_path / "state",
            vault_id="main",
            dry_run=True,
            agent=None,
        )
    )

    assert report.created_catalog is True
    assert report.indexed is False
    assert not (tmp_path / "state").exists()
    assert factory.calls == []


def test_setup_creates_catalog_and_runs_index(tmp_path: Path) -> None:
    factory = RecordingIndexFactory()

    report = SetupService(index_factory=cast(Any, factory)).setup(
        SetupRequest(
            vault_path=make_vault(tmp_path),
            state_path=tmp_path / "state",
            vault_id="main",
            agent=None,
        )
    )

    assert report.indexed is True
    assert factory.calls[0]["initialize_store"] is True
    scope = cast(QueryScope, factory.index_service.calls[0]["scope"])
    assert scope.vault_ids == ("main",)
    assert factory.bundles[0].closed is True


def test_setup_with_agent_prints_config_warning_when_no_config_path(tmp_path: Path) -> None:
    report = SetupService(index_factory=cast(Any, RecordingIndexFactory())).setup(
        SetupRequest(
            vault_path=make_vault(tmp_path),
            state_path=tmp_path / "state",
            vault_id="main",
            agent="codex",
        )
    )

    assert report.mcp_config is not None
    assert report.warnings == ("mcp_config_not_written",)


def test_setup_with_mcp_auto_registers_default_codex_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model = "gpt-5"\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    report = SetupService(index_factory=cast(Any, RecordingIndexFactory())).setup(
        SetupRequest(
            vault_path=make_vault(tmp_path),
            state_path=tmp_path / "state",
            vault_id="main",
            agent="codex",
            register_mcp=True,
        )
    )

    assert report.mcp_registration is not None
    assert report.mcp_registration.config_path == config_path
    assert report.mcp_registration.changed is True
    assert report.mcp_registration.backup_path == config_path.with_name("config.toml.bak")
    assert report.warnings == ()
    config_text = config_path.read_text(encoding="utf-8")
    assert 'model = "gpt-5"' in config_text
    assert "[mcp_servers.vault-graph]" in config_text
    assert 'command = "vg"' in config_text
    assert 'args = ["serve", "--mcp", "--state", ' in config_text
