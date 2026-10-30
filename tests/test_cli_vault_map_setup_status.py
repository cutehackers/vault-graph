"""`vg setup` and `vg status` read vault-map.json (spec 4.2.2, A-9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_setup import _deterministic_text_embeddings
from tests.test_vault_map import fixture_files_stay_unchanged as fixture_files_stay_unchanged
from tests.test_vault_map import make_vaults, render_fixture
from vault_graph.cli.main import app
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV

runner = CliRunner()


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path.resolve()


@pytest.fixture
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)


def _map(base: Path, name: str = "vault-map-v2.json") -> Path:
    make_vaults(base)
    for vault in ("personal", "team"):
        (base / "vaults" / vault / "wiki" / "page.md").write_text(f"# {vault}\nevidence\n", encoding="utf-8")
    return render_fixture(name, base)


def _catalog_ids(graph_home: Path) -> list[str]:
    text = (graph_home / "configs" / "vaults.yaml").read_text(encoding="utf-8")
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("- vault_id:")]


def _tree(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_setup_without_vault_registers_every_map_vault(base: Path, fake_embeddings: None) -> None:
    vault_map = _map(base)
    graph_home = base / "graph-home"

    result = runner.invoke(
        app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map), "--agent", "codex"]
    )

    assert result.exit_code == 0, result.output
    assert sorted(_catalog_ids(graph_home)) == ["personal", "team"]
    assert "vault_id: personal" in result.stdout
    assert "vault_id: team" in result.stdout
    assert result.stdout.count("mcp_config:") == 1


def test_setup_without_vault_keeps_an_already_registered_path(base: Path, fake_embeddings: None) -> None:
    vault_map = _map(base)
    graph_home = base / "graph-home"
    first = runner.invoke(app, ["setup", "--vault", str(base / "vaults" / "personal"), "--graph-home", str(graph_home)])
    assert first.exit_code == 0, first.output

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map)])

    assert result.exit_code == 0, result.output
    assert _catalog_ids(graph_home) == ["default", "team"]


def test_setup_with_vault_ignores_the_map(base: Path, fake_embeddings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_map = _map(base)
    monkeypatch.setenv(VAULT_MAP_ENV, str(vault_map))
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--vault", str(base / "vaults" / "team"), "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert _catalog_ids(graph_home) == ["default"]
    assert "vault_id: default" in result.stdout


def test_setup_without_vault_reads_map_path_from_environment(
    base: Path, fake_embeddings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(VAULT_MAP_ENV, str(_map(base)))
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert sorted(_catalog_ids(graph_home)) == ["personal", "team"]


def test_setup_without_vault_dry_run_writes_nothing(base: Path) -> None:
    vault_map = _map(base)
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "vault_id: personal" in result.stdout
    assert not graph_home.exists()


@pytest.mark.parametrize("name", [None, "vault-map-broken.json", "vault-map-v1.json"])
def test_setup_without_vault_stops_when_map_is_unusable(base: Path, name: str | None) -> None:
    vault_map = _map(base, name) if name else base / "missing.json"
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map)])

    assert result.exit_code == 1
    assert "--vault" in result.output
    assert not graph_home.exists()


def _initialized_home(base: Path) -> Path:
    graph_home = base / "graph-home"
    result = runner.invoke(app, ["init", "--vault", str(base / "vaults" / "personal"), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    return graph_home


def test_status_shows_map_location_version_and_unregistered_vaults(base: Path) -> None:
    vault_map = _map(base)
    graph_home = _initialized_home(base)
    before = _tree(graph_home)

    text = runner.invoke(app, ["status", "--graph-home", str(graph_home), "--vault-map", str(vault_map)])
    as_json = runner.invoke(
        app, ["status", "--graph-home", str(graph_home), "--vault-map", str(vault_map), "--format", "json"]
    )

    assert text.exit_code == 0, text.output
    assert f"vault_map_path: {vault_map}" in text.stdout
    assert "vault_map_state: loaded" in text.stdout
    assert "vault_map_version: 2" in text.stdout
    assert f"vault_map_unregistered_vault: team {base / 'vaults' / 'team'}" in text.stdout
    assert "vault_map_unregistered_vault: personal" not in text.stdout
    assert as_json.exit_code == 0, as_json.output
    assert json.loads(as_json.stdout)["vault_map"] == {
        "path": str(vault_map),
        "state": "loaded",
        "version": 2,
        "warning": None,
        "unregistered_vaults": [{"name": "team", "path": str(base / "vaults" / "team")}],
    }
    assert _tree(graph_home) == before


def test_status_reports_missing_and_invalid_map(base: Path) -> None:
    make_vaults(base)
    graph_home = _initialized_home(base)
    broken = render_fixture("vault-map-broken.json", base)

    missing = runner.invoke(app, ["status", "--graph-home", str(graph_home), "--vault-map", str(base / "none.json")])
    invalid = runner.invoke(app, ["status", "--graph-home", str(graph_home), "--vault-map", str(broken)])

    assert missing.exit_code == 0, missing.output
    assert "vault_map_state: missing" in missing.stdout
    assert "vault_map_version: None" in missing.stdout
    assert invalid.exit_code == 0, invalid.output
    assert "vault_map_state: invalid" in invalid.stdout
    assert f"vault_map_warning: Vault map {broken} is damaged" in invalid.stdout
    assert not (base / "none.json").exists()
