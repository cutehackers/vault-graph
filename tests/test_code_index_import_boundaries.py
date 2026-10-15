from __future__ import annotations

from pathlib import Path

from tests.test_functional_module_boundaries import assert_policy_imports


def test_code_services_do_not_import_concrete_storage_or_composition() -> None:
    root = Path(__file__).parents[1] / "src" / "vault_graph" / "project" / "code"
    assert_policy_imports(root, forbidden=("vault_graph.storage.local",))
