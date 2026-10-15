"""Enforce functional ownership without forcing a directory per responsibility."""

import ast
import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "package",
    [
        "vault_scope",
        "ingestion",
        "indexing",
        "extraction",
        "projection_publication",
        "retrieval",
        "graph_retrieval",
        "projection",
        "context",
        "answer",
        "memory",
        "code_index",
        "project_context",
        "result_explanation",
        "projection_readiness",
        "projection_diagnostics",
        "runtime_operations",
        "integration_configuration",
        "harness",
    ],
)
def test_functional_policies_do_not_import_composition_or_transports(package: str) -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / package
    assert root.is_dir()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            imports: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom):
                imports = (node.module or "",)
            elif isinstance(node, ast.Import):
                imports = tuple(item.name for item in node.names)
            assert not any(
                name.startswith(
                    (
                        "vault_graph.app",
                        "vault_graph.cli",
                        "vault_graph.mcp",
                        "vault_graph.http",
                    )
                )
                for name in imports
            ), (path, imports)


@pytest.mark.parametrize(
    ("legacy", "owner", "symbol"),
    [
        ("app.graph_retrieval_service", "graph_retrieval.graph_retrieval_service", "GraphRetrievalService"),
        ("app.graph_resource_service", "graph_retrieval.graph_resource_service", "GraphResourceService"),
        ("memory.result_explanation", "result_explanation.result_explanation", "ExplainResultService"),
        ("memory.result_explanation_cache", "result_explanation.result_explanation_cache", "ResultExplanationCache"),
    ],
)
def test_feature_legacy_paths_keep_module_and_class_identity(legacy: str, owner: str, symbol: str) -> None:
    previous = importlib.import_module(f"vault_graph.{legacy}")
    current = importlib.import_module(f"vault_graph.{owner}")
    assert previous is current
    assert getattr(previous, symbol) is getattr(current, symbol)


def test_evidence_linker_does_not_import_search_engines_or_factories() -> None:
    path = Path(__file__).parents[1] / "src/vault_graph/vault_adapter/evidence_linking.py"
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(
                (
                    "vault_graph.app",
                    "vault_graph.retrieval",
                    "vault_graph.graph_retrieval",
                    "graph_search",
                    "vector_search",
                    "vector_index",
                )
            )
