"""`vg setup --no-index` sets up Vaults and MCP without indexing (spec 2026-11-05 A-4, A-6, A-8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_vault_map import make_vaults, render_fixture
from vault_graph.interface.cli.main import app
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.interface.mcp.mcp_tools import SearchVaultInput
from vault_graph.operation.runtime.setup_service import SetupRequest, SetupService

runner = CliRunner()


class _IndexFactoryMustNotOpen:
    def open(self, **kwargs: object) -> object:
        raise AssertionError(f"index factory opened during --no-index setup: {kwargs}")


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path.resolve()


@pytest.fixture
def no_index_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Any attempt to index fails the test, so --no-index must skip the index factory entirely.
    monkeypatch.setattr(
        "vault_graph.interface.cli.main.LocalIndexServiceFactory", lambda **_: _IndexFactoryMustNotOpen()
    )


def _map(base: Path) -> Path:
    make_vaults(base)
    for vault in ("personal", "team"):
        (base / "vaults" / vault / "wiki" / "page.md").write_text(f"# {vault}\nevidence\n", encoding="utf-8")
    return render_fixture("vault-map-v2.json", base)


def _catalog_ids(graph_home: Path) -> list[str]:
    text = (graph_home / "configs" / "vaults.yaml").read_text(encoding="utf-8")
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("- vault_id:")]


def test_setup_service_skips_index_when_run_index_is_false(base: Path) -> None:
    vault_root = base / "vault"
    vault_root.mkdir()
    graph_home = base / "graph-home"
    service = SetupService(index_factory=_IndexFactoryMustNotOpen())  # type: ignore[arg-type]

    report = service.setup(SetupRequest(vault_path=vault_root, graph_home_path=graph_home, run_index=False))

    assert report.index_report is None
    assert report.indexed is False
    assert report.ready is False
    assert "vg index --all-vaults" in (report.recovery_hint or "")


def test_setup_request_indexes_by_default() -> None:
    assert SetupRequest(vault_path=Path("v"), graph_home_path=Path("g")).run_index is True


def test_setup_service_dry_run_hint_comes_first_with_run_index_false(base: Path) -> None:
    vault_root = base / "vault"
    vault_root.mkdir()
    service = SetupService(index_factory=_IndexFactoryMustNotOpen())  # type: ignore[arg-type]

    report = service.setup(
        SetupRequest(vault_path=vault_root, graph_home_path=base / "graph-home", run_index=False, dry_run=True)
    )

    assert report.recovery_hint is not None
    assert report.recovery_hint.startswith("run setup without --dry-run")


def test_setup_no_index_registers_vaults_and_mcp_without_indexing(base: Path, no_index_factory: None) -> None:
    vault_map = _map(base)
    graph_home = base / "graph-home"
    mcp_config = base / "claude.json"

    result = runner.invoke(
        app,
        [
            "setup",
            "--graph-home",
            str(graph_home),
            "--vault-map",
            str(vault_map),
            "--agent",
            "claude",
            "--mcp",
            "--no-index",
            "--mcp-config-path",
            str(mcp_config),
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(_catalog_ids(graph_home)) == ["personal", "team"]
    assert not (graph_home / "metadata" / "metadata.sqlite3").exists()
    assert "vault-graph" in json.loads(mcp_config.read_text(encoding="utf-8"))["mcpServers"]
    assert result.stdout.count("indexed: False") == 2
    hints = [line for line in result.stdout.splitlines() if line.startswith("recovery_hint:")]
    assert len(hints) == 2
    assert all("vg index --all-vaults" in line for line in hints)

    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))
    with pytest.raises(McpProtocolError) as exc_info:
        registered.tool_registry.search_vault(SearchVaultInput(query="evidence"))
    assert exc_info.value.payload.code in {"metadata_unavailable", "keyword_index_unavailable"}


def test_setup_no_index_dry_run_creates_nothing(base: Path, no_index_factory: None) -> None:
    vault_map = _map(base)
    graph_home = base / "graph-home"

    result = runner.invoke(
        app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map), "--no-index", "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert "recovery_hint: run setup without --dry-run" in result.stdout
    assert not graph_home.exists()


def test_setup_help_names_no_index_and_the_index_command() -> None:
    result = runner.invoke(app, ["setup", "--help"], env={"COLUMNS": "200", "TERM": "dumb"})

    assert result.exit_code == 0, result.output
    assert "--no-index" in result.stdout
    assert "vg index --all-vaults" in result.stdout
