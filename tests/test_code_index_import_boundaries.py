from __future__ import annotations

from pathlib import Path


def test_code_services_do_not_import_concrete_storage_or_composition() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / "code_index"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    for forbidden in ("vault_graph.storage.local", "vault_graph.app", "vault_graph.mcp", "vault_graph.http"):
        assert forbidden not in source
