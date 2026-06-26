from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.app.watch_service import WatchIterationReport, WatchReport, WatchService
from vault_graph.cli.main import app
from vault_graph.ingestion.vault_catalog import QueryScope

runner = CliRunner()


def test_cli_watch_delegates_selected_scope_without_running_forever(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    seen: dict[str, object] = {}

    def fake_run(
        self: WatchService,
        *,
        scope: QueryScope,
        interval_seconds: float,
        full: bool = False,
        max_iterations: int | None = None,
    ) -> WatchReport:
        del self, max_iterations
        seen["scope"] = scope
        seen["interval_seconds"] = interval_seconds
        seen["full"] = full
        return WatchReport(
            iterations=(
                WatchIterationReport(
                    iteration=1,
                    exit_code=0,
                    index_revision="metadata-1",
                    changed=1,
                    unchanged=2,
                    deleted=0,
                    vector_failed=False,
                    graph_failed=False,
                ),
            ),
            interrupted=False,
        )

    monkeypatch.setattr("vault_graph.app.watch_service.WatchService.run", fake_run)

    result = runner.invoke(
        app,
        ["watch", "--state", str(state_path), "--vault-id", "default", "--interval", "1.5", "--full"],
    )

    assert result.exit_code == 0
    assert seen["interval_seconds"] == 1.5
    assert seen["full"] is True
    assert isinstance(seen["scope"], QueryScope)
    assert seen["scope"].vault_ids == ("default",)
    assert "iteration: 1" in result.stdout
    assert "index_revision: metadata-1" in result.stdout


def test_cli_watch_rejects_conflicting_scope_flags(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["watch", "--state", str(tmp_path / "state"), "--vault-id", "main", "--all-vaults"],
    )

    assert result.exit_code == 1
    assert "Use either --vault-id or --all-vaults, not both." in result.stdout
