from __future__ import annotations

from pathlib import Path

from tests.test_functional_module_boundaries import assert_policy_imports


def test_project_context_application_modules_do_not_import_storage_or_mcp() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / "project" / "context"
    assert_policy_imports(root, forbidden=("vault_graph.storage",))
