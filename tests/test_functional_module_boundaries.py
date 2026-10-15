"""Enforce functional ownership without forcing a directory per responsibility."""

import ast
import importlib
from pathlib import Path

import pytest

# These defaults already exist for direct service construction. Keep the exception
# specific to each local import, rather than allowing composition dependencies.
_ALLOWED_LAZY_DEFAULTS = {
    ("operation/runtime/setup_service.py", "__init__"): (
        "vault_graph.interface.composition.adapters.runtime_indexing",
        {"default_index_factory"},
    ),
    ("operation/runtime/watch_service.py", "__init__"): (
        "vault_graph.interface.composition.adapters.runtime_indexing",
        {"default_index_factory"},
    ),
    ("project/code/code_projection_service.py", "__init__"): (
        "vault_graph.interface.composition.adapters.code_projection_storage",
        {"open_code_projection_reader", "open_code_projection_writer"},
    ),
    ("project/code/code_freshness.py", "_open_store"): (
        "vault_graph.interface.composition.adapters.code_projection_storage",
        {"open_code_projection_reader"},
    ),
}


def assert_policy_imports(root: Path, *, forbidden: tuple[str, ...] = ()) -> None:
    assert root.is_dir()
    paths = tuple(root.rglob("*.py"))
    assert paths
    for path in paths:
        source_path = path.relative_to(Path(__file__).parents[1] / "src" / "vault_graph").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom):
                imports = (node.module or "",)
                for function in ast.walk(tree):
                    if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    allowed = _ALLOWED_LAZY_DEFAULTS.get((source_path, function.name))
                    if (
                        allowed is not None
                        and node in ast.walk(function)
                        and node.module == allowed[0]
                        and {alias.name for alias in node.names} == allowed[1]
                    ):
                        imports = ()
                        break
            elif isinstance(node, ast.Import):
                imports = tuple(item.name for item in node.names)
            forbidden_prefixes = (
                "vault_graph.app",
                "vault_graph.cli",
                "vault_graph.mcp",
                "vault_graph.http",
                "vault_graph.interface",
                *forbidden,
            )
            assert not any(name.startswith(forbidden_prefixes) for name in imports), (path, imports)


@pytest.mark.parametrize(
    "package",
    [
        "operation/scope",
        "indexing/ingestion",
        "indexing",
        "indexing/extraction",
        "indexing/publication",
        "retrieval/search",
        "retrieval/graph",
        "context/pack",
        "context/answer",
        "context/memory",
        "project/code",
        "project/context",
        "retrieval/explanation",
        "operation/readiness",
        "operation/diagnostics",
        "operation/runtime",
        "operation/integration",
        "retrieval/evidence",
    ],
)
def test_functional_policies_do_not_import_composition_or_transports(package: str) -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / package
    assert_policy_imports(root)


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
    path = Path(__file__).parents[1] / "src/vault_graph/retrieval/evidence/evidence_linking.py"
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(
                (
                    "vault_graph.app",
                    "vault_graph.interface",
                    "vault_graph.retrieval.search",
                    "vault_graph.retrieval.graph.graph_retrieval_service",
                    "vault_graph.retrieval.graph.graph_resource_service",
                    "vault_graph.retrieval.graph.projection",
                    "vault_graph.graph_retrieval",
                    "graph_search",
                    "vector_search",
                    "vector_index",
                )
            )
