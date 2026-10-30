"""Policy modules remain usable without the application composition layer."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("package", ["operation/scope", "operation/readiness", "indexing/publication"])
def test_foundation_policy_does_not_import_application_or_transport(package: str) -> None:
    root = Path("src/vault_graph") / package
    assert root.is_dir()
    paths = tuple(root.rglob("*.py"))
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("vault_graph.interface",)), path
                if package == "operation/readiness":
                    assert not (node.module or "").startswith(
                        (
                            "vault_graph.retrieval.search",
                            "vault_graph.retrieval.graph.graph_retrieval_service",
                            "vault_graph.retrieval.graph.graph_resource_service",
                            "vault_graph.retrieval.graph.projection",
                        )
                    ), path


@pytest.mark.parametrize(
    "owner",
    [
        "indexing.index_service",
        "context.answer.answer_service",
        "operation.diagnostics.index_status_reader",
        "operation.diagnostics.projection_hygiene_service",
        "operation.diagnostics.health_explorer",
    ],
)
def test_feature_owner_does_not_import_composition(owner: str) -> None:
    source = Path("src/vault_graph") / f"{owner.replace('.', '/')}.py"
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("vault_graph.interface")
