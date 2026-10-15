"""Policy modules remain usable without the application composition layer."""

import ast
import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize("package", ["vault_scope", "projection_readiness", "projection_publication"])
def test_foundation_policy_does_not_import_application_or_transport(package: str) -> None:
    root = Path("src/vault_graph") / package
    assert root.is_dir()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(
                    ("vault_graph.app", "vault_graph.cli", "vault_graph.mcp", "vault_graph.http")
                ), path
                if package == "projection_readiness":
                    assert not (node.module or "").startswith("vault_graph.retrieval"), path


@pytest.mark.parametrize(
    ("legacy", "owner", "symbol"),
    [
        ("app.catalog_service", "vault_scope.catalog_service", "CatalogService"),
        ("app.graph_home", "vault_scope.graph_home", "GraphHomeResolver"),
        ("app.path_guard", "vault_scope.path_guard", "assert_target_outside_vaults"),
        ("app.graph_readiness_service", "projection_readiness.graph_readiness_service", "ReadOnlyGraphReadiness"),
        ("app.search_readiness_service", "projection_readiness.search_readiness_service", "ReadOnlySearchReadiness"),
        ("app.projection_generation", "projection_publication.projection_generation", "ProjectionGenerationManager"),
        ("retrieval.search_readiness", "projection_readiness.search_readiness", "SearchReadinessReport"),
        ("retrieval.search_response", "projection_readiness.search_readiness", "SearchStoreRevision"),
    ],
)
def test_legacy_imports_preserve_public_class_identity(legacy: str, owner: str, symbol: str) -> None:
    old_module = importlib.import_module(f"vault_graph.{legacy}")
    new_module = importlib.import_module(f"vault_graph.{owner}")
    assert getattr(old_module, symbol) is getattr(new_module, symbol)
    if legacy != "retrieval.search_response":
        assert old_module is new_module


@pytest.mark.parametrize(
    ("legacy", "owner", "symbol"),
    [
        ("app.index_service", "indexing.index_service", "IndexService"),
        ("app.answer_service", "answer.answer_service", "AnswerService"),
        ("app.index_status_reader", "projection_diagnostics.index_status_reader", "StatusReport"),
        (
            "app.projection_hygiene_service",
            "projection_diagnostics.projection_hygiene_service",
            "ProjectionHygieneService",
        ),
        ("memory.health_explorer", "projection_diagnostics.health_explorer", "HealthExplorerService"),
    ],
)
def test_feature_placement_preserves_legacy_module_and_class(legacy: str, owner: str, symbol: str) -> None:
    old_module = importlib.import_module(f"vault_graph.{legacy}")
    new_module = importlib.import_module(f"vault_graph.{owner}")
    assert old_module is new_module
    assert getattr(old_module, symbol) is getattr(new_module, symbol)
    source = Path("src/vault_graph") / f"{owner.replace('.', '/')}.py"
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("vault_graph.app")
