from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


def test_context_package_does_not_import_local_backends_or_llms() -> None:
    forbidden_prefixes = (
        "vault_graph.storage.local",
        "vault_graph.cli",
        "vault_graph.projection.rustworkx_projection",
        "rustworkx",
        "chromadb",
        "openai",
        "anthropic",
    )
    imported_modules: set[str] = set()
    for path in Path("src/vault_graph/context").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    assert not [
        module
        for module in imported_modules
        if any(module == forbidden or module.startswith(f"{forbidden}.") for forbidden in forbidden_prefixes)
    ]


def test_context_package_import_does_not_eagerly_import_concrete_backends() -> None:
    code = """
import sys
import vault_graph.context
for name in (
    'vault_graph.graph',
    'vault_graph.graph.graph_contracts',
    'vault_graph.graph.graph_identity',
    'vault_graph.graph.graph_query',
    'vault_graph.cli.main',
    'vault_graph.storage.local.sqlite_metadata_store',
    'vault_graph.storage.local.chroma_vector_store',
    'vault_graph.retrieval.graph_retrieval',
    'vault_graph.retrieval.graph_candidates',
    'vault_graph.projection.rustworkx_projection',
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_context_package_public_dir_lists_lazy_builder_exports() -> None:
    import vault_graph.context

    assert "SearchContextPackBuilder" in dir(vault_graph.context)
