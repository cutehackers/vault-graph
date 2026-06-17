from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_read_only_boundary import file_bytes
from vault_graph.cli.main import app

runner = CliRunner()


def test_mcp_factory_opens_read_only_services_without_creating_missing_state(tmp_path: Path) -> None:
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    before = file_bytes(vault_root)

    services = McpServiceFactory(state_path=state_path).open_read_only()

    assert services.catalog.active_vault_id == "default"
    assert services.retrieval_service is not None
    assert services.context_pack_builder is not None
    assert file_bytes(vault_root) == before
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_mcp_factory_missing_catalog_fails_without_creating_state(tmp_path: Path) -> None:
    from vault_graph.errors import CatalogError
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    state_path = tmp_path / "missing-state"

    with pytest.raises(CatalogError):
        McpServiceFactory(state_path=state_path).open_read_only()

    assert not state_path.exists()


def test_mcp_factory_uses_read_only_store_constructors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vault_graph.mcp.mcp_service_factory import McpServiceFactory

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    calls: dict[str, object] = {}

    class FakeMetadataStore:
        def __init__(self, path: Path, *, initialize: bool = False) -> None:
            calls["metadata"] = (path, initialize)

    class FakeKeywordIndex:
        def __init__(self, path: Path) -> None:
            calls["keyword"] = path

    class FakeVectorStore:
        def __init__(self, path: Path, *, initialize: bool = False, read_only: bool = False) -> None:
            calls["vector"] = (path, initialize, read_only)

    monkeypatch.setattr("vault_graph.storage.local.sqlite_metadata_store.SQLiteMetadataStore", FakeMetadataStore)
    monkeypatch.setattr("vault_graph.storage.local.sqlite_keyword_index.SQLiteKeywordIndex", FakeKeywordIndex)
    monkeypatch.setattr("vault_graph.storage.local.chroma_vector_store.ChromaVectorStore", FakeVectorStore)

    McpServiceFactory(state_path=state_path).open_read_only()

    assert calls["metadata"] == (state_path / "metadata" / "metadata.sqlite3", False)
    assert calls["keyword"] == state_path / "metadata" / "metadata.sqlite3"
    assert calls["vector"] == (state_path / "vector" / "chroma", False, True)


def test_mcp_factory_open_read_only_does_not_import_rustworkx_projection() -> None:
    code = """
from pathlib import Path
import sys
from vault_graph.mcp.mcp_service_factory import McpServiceFactory
try:
    McpServiceFactory(state_path=Path('/definitely/missing/state')).open_read_only()
except Exception:
    pass
for name in ('vault_graph.projection.rustworkx_projection', 'rustworkx'):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_factory_open_read_only_does_not_import_runtime_clients(tmp_path: Path) -> None:
    code = f"""
from pathlib import Path
import sys
from typer.testing import CliRunner
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_service_factory import McpServiceFactory

vault_root = Path({str(tmp_path / "vault")!r})
vault_root.mkdir()
state_path = Path({str(tmp_path / "state")!r})
runner = CliRunner()
runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
McpServiceFactory(state_path=state_path).open_read_only()
for name in ("chromadb", "fastembed", "huggingface_hub", "rustworkx"):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_factory_graph_service_imports_rustworkx_only_when_requested(tmp_path: Path) -> None:
    code = f"""
from pathlib import Path
import sys
from typer.testing import CliRunner
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_service_factory import McpServiceFactory

vault_root = Path({str(tmp_path / "vault")!r})
(vault_root / "wiki").mkdir(parents=True)
(vault_root / "wiki" / "page.md").write_text("# Page\\nBody\\n", encoding="utf-8")
state_path = Path({str(tmp_path / "state")!r})
runner = CliRunner()
runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
factory = McpServiceFactory(state_path=state_path)
factory.open_read_only()
if "vault_graph.projection.rustworkx_projection" in sys.modules:
    raise SystemExit("eager")
try:
    factory.open_graph_retrieval_service()
except Exception:
    pass
if "vault_graph.projection.rustworkx_projection" not in sys.modules:
    raise SystemExit("missing")
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
