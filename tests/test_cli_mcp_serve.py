from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_serve_help_exposes_mcp_without_starting_server() -> None:
    result = runner.invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--mcp" in result.output
    assert "--state" in result.output


def test_serve_requires_selected_transport(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "select one server transport: --mcp or --http" in result.stderr


def test_serve_http_delegates_to_local_http_server(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    seen: tuple[Path, str, int] | None = None

    def fake_run(config: object) -> None:
        nonlocal seen
        seen = (config.state_path, config.host, config.port)  # type: ignore[attr-defined]

    monkeypatch.setattr("vault_graph.http.http_server.run_http_server", fake_run)

    result = runner.invoke(
        app,
        ["serve", "--http", "--state", str(tmp_path / "state"), "--host", "127.0.0.1", "--port", "9876"],
    )

    assert result.exit_code == 0
    assert seen == ((tmp_path / "state").resolve(), "127.0.0.1", 9876)


def test_serve_rejects_multiple_transports(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", "--mcp", "--http", "--state", str(tmp_path / "state")])

    assert result.exit_code == 1
    assert "Use either --mcp or --http, not both." in result.stderr


def test_serve_mcp_missing_catalog_exits_before_stdio_start(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    called = False

    def fake_run(_: object, *, config: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("vault_graph.mcp.mcp_server.run_mcp_server", fake_run)

    result = runner.invoke(app, ["serve", "--mcp", "--state", str(tmp_path / "missing-state")])

    assert result.exit_code == 1
    assert called is False
    assert "VaultCatalog config does not exist" in result.stderr
    assert result.stdout == ""


def test_serve_mcp_delegates_without_stdout_startup_text(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    seen_state: Path | None = None

    def fake_run(_: object, *, config: object) -> None:
        nonlocal seen_state
        seen_state = config.state_path  # type: ignore[attr-defined]

    monkeypatch.setattr("vault_graph.mcp.mcp_server.run_mcp_server", fake_run)

    result = runner.invoke(app, ["serve", "--mcp", "--state", str(state_path)])

    assert result.exit_code == 0
    assert seen_state == state_path.expanduser().resolve()
    assert result.stdout == ""
