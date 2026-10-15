"""Grouped owners preserve imports and remain safe to load in a fresh process."""

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

OWNERS = (
    ("ingestion.document_models", "indexing.ingestion.document_models"),
    ("extraction.entity_extractor", "indexing.extraction.entity_extractor"),
    ("projection_publication.projection_generation", "indexing.publication.projection_generation"),
    ("retrieval.retrieval_service", "retrieval.search.retrieval_service"),
    ("graph_retrieval.graph_retrieval_service", "retrieval.graph.graph_retrieval_service"),
    ("vault_adapter.evidence_linking", "retrieval.evidence.evidence_linking"),
    ("result_explanation.result_explanation", "retrieval.explanation.result_explanation"),
    ("context.context_pack", "context.pack.context_pack"),
    ("memory.project_memory", "context.memory.project_memory"),
    ("answer.answer_service", "context.answer.answer_service"),
    ("code_index.code_query_service", "project.code.code_query_service"),
    ("project_context.project_context_service", "project.context.project_context_service"),
    ("vault_scope.catalog_service", "operation.scope.catalog_service"),
    ("projection_readiness.search_readiness_service", "operation.readiness.search_readiness_service"),
    ("projection_diagnostics.index_status_reader", "operation.diagnostics.index_status_reader"),
    ("runtime_operations.setup_service", "operation.runtime.setup_service"),
    ("project_context.project_binding_catalog", "operation.integration.project_binding_catalog"),
    ("cli.main", "interface.cli.main"),
    ("mcp.mcp_tools", "interface.mcp.mcp_tools"),
    ("http.http_server", "interface.http.http_server"),
    ("app.read_only_service_factory", "interface.composition.read_only_service_factory"),
    ("embeddings.text_embeddings", "storage.interfaces.text_embeddings"),
    ("vault_adapter.vector_store", "storage.local.vector_store_adapter"),
)


@pytest.mark.parametrize(("legacy", "owner"), OWNERS)
def test_grouped_owner_preserves_legacy_module_identity(legacy: str, owner: str) -> None:
    assert importlib.import_module(f"vault_graph.{legacy}") is importlib.import_module(f"vault_graph.{owner}")


@pytest.mark.parametrize(
    "module",
    (
        "operation.integration.project_binding_catalog",
        "project.context.project_binding",
        "retrieval.graph.graph_contracts",
        "storage.interfaces.metadata_store",
        "retrieval.evidence.evidence_linking",
        "interface.cli.main",
        "interface.mcp.mcp_service_factory",
        "interface.http.http_service_factory",
    ),
)
def test_canonical_entry_imports_without_legacy_initialization_order(module: str) -> None:
    code = f"""
import importlib
import sys
importlib.import_module('vault_graph.{module}')
assert not set(('chromadb', 'fastembed', 'huggingface_hub', 'rustworkx')) & set(sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_all_compatibility_facades_resolve_to_same_canonical_module() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph"
    checked = 0
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "sys.modules[__name__] = _implementation" not in source:
            continue
        legacy = "vault_graph." + ".".join(path.relative_to(root).with_suffix("").parts)
        tree = ast.parse(source)
        target = next(
            f"{node.module}.{item.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for item in node.names
            if item.asname == "_implementation"
        )
        assert importlib.import_module(legacy) is importlib.import_module(target), legacy
        checked += 1
    assert checked >= len(OWNERS)
