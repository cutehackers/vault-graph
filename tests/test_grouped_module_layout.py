"""Only canonical grouped paths remain, and they are safe to load in a fresh process."""

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Previous import paths removed by 보완8 (remediation plan 결정1 옵션1). Only canonical paths remain.
REMOVED_PACKAGES = (
    "answer",
    "app",
    "cli",
    "code_index",
    "embeddings",
    "extraction",
    "graph",
    "graph_retrieval",
    "harness",
    "http",
    "ingestion",
    "integration_configuration",
    "mcp",
    "memory",
    "project_context",
    "projection",
    "projection_diagnostics",
    "projection_publication",
    "projection_readiness",
    "result_explanation",
    "runtime_operations",
    "vault_adapter",
    "vault_scope",
)
REMOVED_MODULES = (
    "context.context_evidence_selection",
    "context.context_pack",
    "context.context_pack_builder",
    "context.context_pack_renderer",
    "context.context_pack_serialization",
    "context.context_pack_warnings",
    "retrieval.candidate_ranking",
    "retrieval.context_expansion",
    "retrieval.evidence_result_assembly",
    "retrieval.graph_candidates",
    "retrieval.graph_retrieval",
    "retrieval.retrieval_candidate",
    "retrieval.retrieval_result",
    "retrieval.retrieval_service",
    "retrieval.search_readiness",
    "retrieval.search_response",
    "indexing.vector_indexer",
)


@pytest.mark.parametrize("module", REMOVED_PACKAGES + REMOVED_MODULES)
def test_previous_import_path_is_removed(module: str) -> None:
    assert importlib.util.find_spec(f"vault_graph.{module}") is None


@pytest.mark.parametrize(("group", "name"), (("context", "ContextPack"), ("retrieval", "RetrievalService")))
def test_group_package_does_not_re_export_previous_names(group: str, name: str) -> None:
    assert not hasattr(importlib.import_module(f"vault_graph.{group}"), name)


def test_no_compatibility_facade_remains() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph"
    facades = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "sys.modules[__name__]" in path.read_text(encoding="utf-8")
    ]
    assert facades == []


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
