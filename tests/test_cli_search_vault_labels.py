"""V2 on the CLI: `vg search`, `vg ask` and `vg context` without a Vault option use the cwd project's Vaults."""

import json
import subprocess
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, write_page
from vault_graph.interface.cli.main import app
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: MonkeyPatch) -> tuple[Path, Path]:
    """Graph Home with active Vault ``first`` and Vaults ``second``, ``third`` linked to a git repo."""
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    for name in ("first", "second", "third"):
        write_page(tmp_path / name, "wiki/same.md", f"# Same\nGraphRAG from {name}\n")
    graph_home = tmp_path / "state"
    first, second, third = (str(tmp_path / name) for name in ("first", "second", "third"))
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", first, "--graph-home", str(graph_home)])
    runner.invoke(app, ["vault", "add", "second", "--path", second, "--graph-home", str(graph_home)])
    runner.invoke(app, ["vault", "add", "third", "--path", third, "--graph-home", str(graph_home)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home), "--all-vaults"])
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (tmp_path / "unregistered").mkdir()
    map_file = tmp_path / "vault-map.json"
    map_file.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "personal-notes": {"path": second, "role": "personal"},
                    "team-notes": {"path": third, "role": "team"},
                    "first-notes": {"path": first, "role": "project"},
                    "unregistered": {"path": str(tmp_path / "unregistered"), "role": "project"},
                },
                "projects": {"repo": {"root": str(repo), "vaults": ["personal-notes", "team-notes"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(VAULT_MAP_ENV, str(map_file))
    return graph_home, repo


def _search_json(graph_home: Path, *options: str) -> dict[str, object]:
    result = runner.invoke(app, ["search", "--graph-home", str(graph_home), "--format", "json", *options, "GraphRAG"])
    assert result.exit_code == 0, result.stdout
    payload: dict[str, object] = json.loads(result.stdout)
    return payload


def test_search_in_a_project_folder_returns_one_list_from_every_project_vault(
    project: tuple[Path, Path], monkeypatch: MonkeyPatch
) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo)

    payload = _search_json(graph_home)

    results = payload["results"]
    assert isinstance(results, list)
    assert sorted(item["vault_id"] for item in results) == ["second", "third"]
    labels = {item["vault_id"]: (item["vault_name"], item["vault_role"]) for item in results}
    assert labels == {"second": ("personal-notes", "personal"), "third": ("team-notes", "team")}
    assert [item["rank"] for item in results] == [1, 2]


def test_search_outside_a_project_uses_the_active_vault(project: tuple[Path, Path], monkeypatch: MonkeyPatch) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo.parent)

    payload = _search_json(graph_home)

    results = payload["results"]
    assert isinstance(results, list)
    assert [(item["vault_id"], item["vault_name"], item["vault_role"]) for item in results] == [
        ("first", "first-notes", "project")
    ]


def test_explicit_vault_option_keeps_its_scope_and_adds_only_labels(
    project: tuple[Path, Path], monkeypatch: MonkeyPatch
) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo)

    payload = _search_json(graph_home, "--vault-id", "first")

    results = payload["results"]
    assert isinstance(results, list)
    assert [item["vault_id"] for item in results] == ["first"]
    assert (results[0]["vault_name"], results[0]["vault_role"]) == ("first-notes", "project")
    assert payload["warnings"] == []


def test_text_result_lines_start_with_vault_name_and_role(project: tuple[Path, Path], monkeypatch: MonkeyPatch) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home), "GraphRAG"])

    assert result.exit_code == 0
    result_lines = [line for line in result.stdout.splitlines() if "wiki/same.md#" in line and ". [" in line]
    assert len(result_lines) == 2
    assert {line.split("] ", 1)[0] + "]" for line in result_lines} == {"[personal-notes·personal]", "[team-notes·team]"}


def test_vault_missing_from_the_map_has_null_labels_and_no_text_prefix(
    project: tuple[Path, Path], monkeypatch: MonkeyPatch
) -> None:
    graph_home, _ = project
    monkeypatch.setenv(VAULT_MAP_ENV, str(graph_home / "missing.json"))

    payload = _search_json(graph_home)
    text = runner.invoke(app, ["search", "--graph-home", str(graph_home), "GraphRAG"]).stdout

    results = payload["results"]
    assert isinstance(results, list)
    assert (results[0]["vault_name"], results[0]["vault_role"]) == (None, None)
    assert "1. [first]" in text


def test_project_without_registered_vault_returns_empty_results_and_setup_warning(
    project: tuple[Path, Path], tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    graph_home, repo = project
    map_file = tmp_path / "vault-map.json"
    data = json.loads(map_file.read_text(encoding="utf-8"))
    data["projects"]["repo"]["vaults"] = ["unregistered"]
    map_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.chdir(repo)

    payload = _search_json(graph_home)
    text = runner.invoke(app, ["search", "--graph-home", str(graph_home), "GraphRAG"]).stdout

    assert payload["results"] == []
    assert payload["result_count"] == 0
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert any("vg setup" in warning["message"] and "unregistered" in warning["message"] for warning in warnings)
    assert "results: 0" in text
    assert "vg setup" in text


def test_context_in_a_project_folder_uses_the_project_vaults(
    project: tuple[Path, Path], monkeypatch: MonkeyPatch
) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["context", "--graph-home", str(graph_home), "--format", "json", "GraphRAG"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["scope"]["requested"]["vault_ids"] == ["second", "third"]


def test_ask_in_a_project_folder_uses_the_project_vaults(project: tuple[Path, Path], monkeypatch: MonkeyPatch) -> None:
    graph_home, repo = project
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["ask", "--graph-home", str(graph_home), "--format", "json", "GraphRAG?"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert {item["vault_id"] for item in payload["evidence"]} <= {"second", "third"}
    assert payload["evidence"]
