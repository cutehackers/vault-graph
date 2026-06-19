from __future__ import annotations

import subprocess
import sys


def test_mcp_package_import_is_lazy() -> None:
    code = """
import sys
import vault_graph.mcp
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'vault_graph.context.context_pack_builder',
    'vault_graph.retrieval.retrieval_service',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_mcp_service_factory_module_import_is_lightweight() -> None:
    code = """
import sys
import vault_graph.mcp.mcp_service_factory
for name in (
    'vault_graph.retrieval.retrieval_service',
    'vault_graph.context.context_pack_builder',
    'vault_graph.app.index_service',
    'vault_graph.app.graph_retrieval_service',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'chromadb',
    'fastembed',
    'huggingface_hub',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_result_explanation_module_import_is_mcp_free() -> None:
    code = """
import sys
import vault_graph.memory.result_explanation
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'mem0',
    'memmachine',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
