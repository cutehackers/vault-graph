import subprocess
import sys
from pathlib import Path


def test_retrieval_package_does_not_import_indexing_or_local_status_store() -> None:
    retrieval_files = Path("src/vault_graph/retrieval").glob("*.py")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in retrieval_files)

    assert "vault_graph.app" not in combined
    assert "vault_graph.indexing" not in combined
    assert "vector_status_store" not in combined
    assert "ReadOnlySearchReadiness" not in combined


def test_cli_graph_retrieval_boundary_stays_at_app_and_dto_level() -> None:
    source = Path("src/vault_graph/cli/main.py").read_text(encoding="utf-8")

    assert "GraphRetrievalService" in source
    assert "RelatedResponse" in source
    assert "DecisionTraceResponse" in source
    assert "import rustworkx" not in source
    assert "from rustworkx" not in source


def test_cli_import_does_not_load_rustworkx_projection_adapter() -> None:
    script = """
import sys
import vault_graph.cli.main
print("vault_graph.projection.rustworkx_projection" in sys.modules)
print("rustworkx" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["False", "False"]


def test_graph_projection_does_not_import_sqlite_stores() -> None:
    projection_files = Path("src/vault_graph/projection").glob("*.py")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in projection_files)

    assert "vault_graph.storage.local" not in combined
    assert "SQLite" not in combined


def test_graph_retrieval_service_uses_interfaces_not_local_sqlite_helpers() -> None:
    source = Path("src/vault_graph/app/graph_retrieval_service.py").read_text(encoding="utf-8")

    assert "vault_graph.storage.interfaces.graph_store" in source
    assert "vault_graph.storage.interfaces.metadata_store" in source
    assert "vault_graph.storage.local" not in source
    assert "SQLite" not in source


def test_retrieval_service_depends_on_graph_candidate_provider_not_sqlite_graph_store() -> None:
    source = Path("src/vault_graph/retrieval/retrieval_service.py").read_text(encoding="utf-8")

    assert "GraphCandidateProvider" in source
    assert "SQLiteGraphStore" not in source
    assert "vault_graph.storage.local.sqlite_graph_store" not in source
