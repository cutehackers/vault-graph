from __future__ import annotations

from pathlib import Path


def test_project_context_application_modules_do_not_import_storage_or_mcp() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / "project_context"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "vault_graph.storage" not in source
    assert "vault_graph.mcp" not in source
