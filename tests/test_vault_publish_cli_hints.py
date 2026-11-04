from __future__ import annotations

from vault_graph.interface.composition.adapters.vault_publish_cli import MIGRATE_MESSAGE, PROPOSE_MIGRATE_MESSAGE


def test_migrate_hints_name_the_vault_builder_command_that_works_from_any_folder() -> None:
    for message in (MIGRATE_MESSAGE, PROPOSE_MIGRATE_MESSAGE):
        assert "`vault-builder audit --target <vault> --plan-out <plan.json>`" in message
        assert "`vault-builder apply --target <vault> --plan <plan.json>`" in message
        assert "tools/vault_migration/cli.py" not in message
