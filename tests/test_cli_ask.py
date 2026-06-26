from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_answer_response_contract import make_response
from vault_graph.answer.answer_plan import AnswerRequest
from vault_graph.cli.main import app
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry

runner = CliRunner()


class RecordingAnswerService:
    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []

    def ask(self, request: AnswerRequest) -> object:
        self.requests.append(request)
        return make_response()


def fake_catalog(tmp_path: Path) -> VaultCatalog:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    return VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root),),
        active_vault_id="main",
    )


def test_cli_ask_uses_active_vault_by_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    service = RecordingAnswerService()
    catalog = fake_catalog(tmp_path)
    monkeypatch.setattr("vault_graph.cli.main._catalog", lambda state: (object(), catalog))
    monkeypatch.setattr(
        "vault_graph.cli.main._answer_service",
        lambda state, include_graph=False: (object(), catalog, service),
        raising=False,
    )

    result = runner.invoke(app, ["ask", "--state", str(tmp_path / "state"), "Why GraphRAG?"])

    assert result.exit_code == 0
    assert service.requests[0].requested_scope.vault_ids == ("main",)
    assert "status: supported" in result.stdout


def test_cli_ask_json_uses_answer_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    service = RecordingAnswerService()
    catalog = fake_catalog(tmp_path)
    monkeypatch.setattr("vault_graph.cli.main._catalog", lambda state: (object(), catalog))
    monkeypatch.setattr(
        "vault_graph.cli.main._answer_service",
        lambda state, include_graph=False: (object(), catalog, service),
        raising=False,
    )

    result = runner.invoke(app, ["ask", "--state", str(tmp_path / "state"), "--format", "json", "Why GraphRAG?"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["answer_status"] == "supported"
    assert payload["evidence"][0]["vault_id"] == "main"


def test_cli_ask_scope_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["ask", "--state", str(tmp_path / "state"), "--vault-id", "main", "--all-vaults", "Why GraphRAG?"],
    )

    assert result.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in result.stdout


def test_cli_ask_include_cross_vault_requires_all_vaults_and_graph(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ask", "--state", str(tmp_path / "state"), "--include-cross-vault", "Why GraphRAG?"])

    assert result.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in result.stdout


def test_cli_ask_rejects_empty_question(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ask", "--state", str(tmp_path / "state"), "   "])

    assert result.exit_code == 1
    assert "empty_question" in result.stdout


def test_cli_ask_rejects_unsupported_format(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ask", "--state", str(tmp_path / "state"), "--format", "xml", "Why?"])

    assert result.exit_code == 1
    assert "unsupported_format" in result.stdout


def test_vg_help_lists_ask_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ask" in result.output
