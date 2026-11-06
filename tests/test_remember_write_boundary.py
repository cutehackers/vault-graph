"""A-15: only the memory write tools (``remember``, ``update_memory``, ``retire_memory``) may run publish-draft.

Every test in this module runs with a publisher that fails the test when it is called. The
existing MCP read-only boundary tests and the ``vg index`` boundary test are imported here so
they run again under that publisher. ``vg watch`` runs one real iteration under it too.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests import test_mcp_tool_read_only_boundary as mcp_read_only
from tests import test_read_only_boundary as read_only
from tests.test_read_only_boundary import _fake_text_embeddings, file_bytes
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.operation.runtime.watch_service import WatchReport, WatchService
from vault_graph.operation.scope.vault_catalog import QueryScope

runner = CliRunner()

# Existing read-only boundary tests, collected again here under the failing publisher.
_REUSED_TESTS = {
    **{name: test for name, test in vars(mcp_read_only).items() if name.startswith("test_")},
    "test_index_commands_do_not_modify_vault_files": read_only.test_index_commands_do_not_modify_vault_files,
}
globals().update(_REUSED_TESTS)


class PublisherCalled(AssertionError):
    pass


@pytest.fixture(autouse=True)
def _publisher_fails_when_called(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(self: VaultPublishCli, vault_root: Path, draft_path: Path, *, timeout_s: float) -> object:
        raise PublisherCalled(f"publish-draft must not run here: {vault_root} {draft_path}")

    monkeypatch.setattr(VaultPublishCli, "publish", fail)


def test_failing_publisher_stand_in_is_active(tmp_path: Path) -> None:
    with pytest.raises(PublisherCalled):
        VaultPublishCli().publish(tmp_path, tmp_path / "draft.json", timeout_s=1)


def test_mcp_server_registers_the_memory_write_tools_as_the_only_new_tools(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)]).exit_code == 0

    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home_path))

    # Spec 2026-11-05 §4.4.12: 19 tools. The six Vault write tools come last; the two new cleanup read
    # tools (list_memory_candidates, mark_candidates_reviewed) write only to the Graph Home.
    assert len(registered.tool_registry.tool_names) == 19
    assert registered.tool_registry.tool_names[-6:] == (
        "remember",
        "update_memory",
        "retire_memory",
        "import_auto_memory",
        "supersede_claim",
        "restore_memory",
    )


def test_watch_one_iteration_does_not_run_the_publisher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vault_graph.interface.composition.local_index_service_factory._default_text_embeddings",
        _fake_text_embeddings,
    )
    original_run = WatchService.run

    def run_once(
        self: WatchService,
        *,
        scope: QueryScope,
        interval_seconds: float,
        full: bool = False,
        max_iterations: int | None = None,
    ) -> WatchReport:
        del max_iterations
        return original_run(self, scope=scope, interval_seconds=interval_seconds, full=full, max_iterations=1)

    monkeypatch.setattr(WatchService, "run", run_once)
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    graph_home_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)]).exit_code == 0
    before = file_bytes(vault_root)

    result = runner.invoke(app, ["watch", "--graph-home", str(graph_home_path), "--interval", "1"])

    assert result.exit_code == 0, result.stdout
    assert "iteration: 1" in result.stdout
    assert file_bytes(vault_root) == before
