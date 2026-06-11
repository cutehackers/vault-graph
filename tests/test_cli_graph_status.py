import json
from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.graph.graph_contracts import current_graph_extraction_spec

runner = CliRunner()


def test_cli_status_reports_graph_readiness_without_creating_graph_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path)])
    spec = current_graph_extraction_spec()

    assert result.exit_code == 0
    assert "graph_backend: sqlite-graph" in result.stdout
    assert "graph_freshness: missing" in result.stdout
    assert "graph_schema_compatible: False" in result.stdout
    assert f"graph_extraction_spec_version: {spec.spec_version}" in result.stdout
    assert f"graph_extraction_spec_digest: {spec.spec_digest}" in result.stdout
    assert not (state_path / "graph").exists()


def test_cli_status_json_reports_graph_readiness(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path), "--format", "json"])
    spec = current_graph_extraction_spec()

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["active_vault_id"] == "default"
    assert payload["graph"]["backend_name"] == "sqlite-graph"
    assert payload["graph"]["freshness"] == "missing"
    assert payload["graph"]["graph_extraction_spec_version"] == spec.spec_version
    assert payload["graph"]["graph_extraction_spec_digest"] == spec.spec_digest
    assert payload["graph"]["scope_readiness"][0]["vault_id"] == "default"
    assert payload["graph"]["scope_readiness"][0]["freshness"] == "missing"
    assert payload["selected_scope"]["vault_ids"] == ["default"]


def test_cli_status_rejects_unknown_format(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0

    result = runner.invoke(app, ["status", "--state", str(state_path), "--format", "xml"])

    assert result.exit_code == 1
    assert "unsupported_format" in result.stdout


def test_cli_status_all_vaults_uses_explicit_graph_scope(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    assert (
        runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)]).exit_code
        == 0
    )
    assert (
        runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)]).exit_code
        == 0
    )

    result = runner.invoke(app, ["status", "--state", str(state_path), "--all-vaults", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["selected_scope"]["vault_ids"] == ["first", "second"]
    assert payload["graph"]["affected_vault_ids"] == ["first", "second"]
    assert [row["vault_id"] for row in payload["graph"]["scope_readiness"]] == ["first", "second"]
