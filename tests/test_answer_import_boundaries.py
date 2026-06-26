from __future__ import annotations

import subprocess
import sys


def test_answer_package_import_is_mcp_and_backend_free() -> None:
    code = """
import sys
import vault_graph.answer
for name in (
    'mcp',
    'mcp.server.fastmcp',
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
