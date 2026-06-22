from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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


def test_memory_models_import_is_backend_and_external_memory_free() -> None:
    code = """
import sys
import vault_graph.memory.memory_models
for name in (
    'mcp',
    'mcp.server.fastmcp',
    'chromadb',
    'fastembed',
    'rustworkx',
    'vault_graph.mcp.mcp_tools',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'mem0',
    'memmachine',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_memory_item_lazy_export_does_not_import_services_or_backends() -> None:
    code = """
import sys
from vault_graph.memory import MemoryItem
if MemoryItem.__name__ != 'MemoryItem':
    raise SystemExit('missing MemoryItem')
for name in (
    'vault_graph.memory.decision_memory',
    'vault_graph.memory.issue_memory',
    'vault_graph.memory.project_memory',
    'vault_graph.app.index_service',
    'vault_graph.mcp.mcp_tools',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.projection.rustworkx_projection',
    'chromadb',
    'fastembed',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_memory_service_module_imports_do_not_pull_index_or_local_backends() -> None:
    code = """
import sys
import vault_graph.memory.decision_memory
import vault_graph.memory.issue_memory
import vault_graph.memory.project_memory
for name in (
    'vault_graph.app.index_service',
    'vault_graph.indexing.metadata_indexer',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.storage.local.sqlite_graph_store',
    'vault_graph.projection.rustworkx_projection',
    'chromadb',
    'fastembed',
    'rustworkx',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_phase_6b_memory_files_do_not_introduce_writable_memory_surfaces() -> None:
    forbidden = (
        "MemoryStore",
        "Memory.create",
        "Memory.query",
        "Memory.upsert",
        "Memory.link",
        "Memory.audit",
        "episode_log",
        "profile_memory",
        "mem0",
        "memmachine",
    )
    repo_root = Path(__file__).resolve().parents[1]
    paths = (
        *sorted((repo_root / "src" / "vault_graph" / "memory").glob("*.py")),
        repo_root / "src" / "vault_graph" / "mcp" / "mcp_memory_serialization.py",
    )

    offenders = [
        (path.relative_to(repo_root), token)
        for path in paths
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
