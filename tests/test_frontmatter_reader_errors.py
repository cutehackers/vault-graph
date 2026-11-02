"""One badly formatted frontmatter block never stops indexing of that Vault or the others."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_setup import _deterministic_text_embeddings
from tests.test_vault_map import make_vaults, render_fixture
from vault_graph.indexing.ingestion.document_models import SourceDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.interface.cli.main import app

runner = CliRunner()

# Real line from a Vault page. YAML rejects it, Vault's own frontmatter parser accepts it.
BAD_FRONTMATTER_PAGE = (
    "---\n"
    "title: Park hub\n"
    'description: "Hub" in 9.81 Park 3.0 planning docs and decisions\n'
    "tags: [park, hub]\n"
    "---\n"
    "# Park hub\n"
    "Park planning evidence\n"
)


def test_invalid_yaml_frontmatter_falls_back_to_vault_rules() -> None:
    projection = read_frontmatter(BAD_FRONTMATTER_PAGE)

    assert projection.data == {
        "title": "Park hub",
        "description": '"Hub" in 9.81 Park 3.0 planning docs and decisions',
        "tags": ["park", "hub"],
    }
    assert projection.body == "# Park hub\nPark planning evidence\n"
    assert projection.yaml_error is not None
    assert projection.yaml_error.startswith("line 3: ")


def test_valid_yaml_frontmatter_has_no_error() -> None:
    projection = read_frontmatter("---\ntitle: Ok\n---\nbody\n")

    assert projection.data == {"title": "Ok"}
    assert projection.yaml_error is None


def test_markdown_reader_warns_for_invalid_yaml() -> None:
    raw = BAD_FRONTMATTER_PAGE.encode("utf-8")
    source = SourceDocument(
        vault_id="main",
        root_path=Path("/vault"),
        path="wiki/park-hub.md",
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )

    extracted = MarkdownDocumentReader().read(source)

    codes = [warning.code for warning in extracted.warnings]
    assert codes == ["frontmatter_invalid_yaml"]
    assert "not valid YAML" in extracted.warnings[0].message
    assert extracted.frontmatter.data["title"] == "Park hub"


@pytest.fixture
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)


def _two_vault_map(base: Path) -> Path:
    make_vaults(base)
    (base / "vaults" / "personal" / "wiki" / "park-hub.md").write_text(BAD_FRONTMATTER_PAGE, encoding="utf-8")
    (base / "vaults" / "personal" / "wiki" / "ok.md").write_text("# Ok\npersonal evidence\n", encoding="utf-8")
    (base / "vaults" / "team" / "wiki" / "page.md").write_text("# team\nteam evidence\n", encoding="utf-8")
    return render_fixture("vault-map-v2.json", base)


def _catalog_ids(graph_home: Path) -> list[str]:
    text = (graph_home / "configs" / "vaults.yaml").read_text(encoding="utf-8")
    return [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("- vault_id:")]


def test_setup_indexes_every_vault_when_one_file_has_invalid_yaml(tmp_path: Path, fake_embeddings: None) -> None:
    base = tmp_path.resolve()
    vault_map = _two_vault_map(base)
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map)])

    assert result.exit_code == 0, result.output
    assert sorted(_catalog_ids(graph_home)) == ["personal", "team"]
    assert "Traceback" not in result.output
    assert "frontmatter_invalid_yaml" in result.output
    assert "wiki/park-hub.md" in result.output
    assert result.stdout.count("ready: True") == 2


def test_index_continues_when_one_file_has_invalid_yaml(tmp_path: Path, fake_embeddings: None) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "park-hub.md").write_text(BAD_FRONTMATTER_PAGE, encoding="utf-8")
    (vault_root / "wiki" / "ok.md").write_text("# Ok\nevidence\n", encoding="utf-8")
    graph_home = tmp_path / "graph-home"
    first = runner.invoke(app, ["setup", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    assert first.exit_code == 0, first.output

    result = runner.invoke(app, ["index", "--graph-home", str(graph_home), "--full"])

    assert result.exit_code == 0, result.output
    assert "wiki/park-hub.md" in result.output
    assert "frontmatter_invalid_yaml" in result.output


def test_setup_continues_to_next_vault_and_reports_failed_vault(tmp_path: Path, fake_embeddings: None) -> None:
    base = tmp_path.resolve()
    vault_map = _two_vault_map(base)
    shutil.rmtree(base / "vaults" / "personal")
    graph_home = base / "graph-home"

    result = runner.invoke(app, ["setup", "--graph-home", str(graph_home), "--vault-map", str(vault_map)])

    assert result.exit_code == 1, result.output
    assert "team" in _catalog_ids(graph_home)
    assert "vault_id: team" in result.stdout
    assert "Traceback" not in result.output
    failed_lines = [line for line in result.output.splitlines() if line.startswith("setup_failed:")]
    assert len(failed_lines) == 1
    assert "personal" in failed_lines[0]
