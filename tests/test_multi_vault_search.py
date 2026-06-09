import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, write_page
from vault_graph.cli.main import app

runner = CliRunner()


def test_all_vault_search_keeps_identical_paths_separate(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/same.md", "# Same\nGraphRAG from first\n")
    write_page(second, "wiki/same.md", "# Same\nGraphRAG from second\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path), "--all-vaults"])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--all-vaults", "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert sorted(item["vault_id"] for item in payload["results"]) == ["first", "second"]
    assert all(item["kind"] == "evidence_chunk" for item in payload["results"])
    assert len({item["result_id"] for item in payload["results"]}) == 2
    assert all(item.get("scope_key") for item in payload["store_revisions"])
    assert all(warning.get("affected_vault_ids") for warning in payload["warnings"])
    assert all(item["vault_id"] in item["result_id"] for item in payload["results"])


def test_single_vault_search_does_not_leak_other_vault_results(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/same.md", "# Same\nGraphRAG from first\n")
    write_page(second, "wiki/same.md", "# Same\nGraphRAG from second\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path), "--all-vaults"])

    result = runner.invoke(
        app,
        ["search", "--state", str(state_path), "--vault-id", "second", "--format", "json", "GraphRAG"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["vault_id"] for item in payload["results"]] == ["second"]
    assert "from second" in payload["results"][0]["summary"]
    assert all(item.get("scope_key") for item in payload["store_revisions"])
    assert all(warning.get("affected_vault_ids") for warning in payload["warnings"])
    assert all(item["vault_id"] in item["result_id"] for item in payload["results"])
