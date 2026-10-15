"""Compatibility defaults for local code projection storage construction."""

from pathlib import Path

from vault_graph.code_index.code_models import CODE_PARSER_SPEC_VERSION
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore
from vault_graph.storage.local.sqlite_code_projection_store import SQLiteCodeProjectionStore


def open_code_projection_reader(
    database_path: Path,
    policy_revision: str | None = None,
    *,
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
) -> CodeProjectionStore:
    return SQLiteCodeProjectionStore.open_read_only(
        database_path, policy_revision=policy_revision, parser_spec_version=parser_spec_version
    )


def open_code_projection_writer(
    database_path: Path,
    policy_revision: str | None = None,
    *,
    parser_spec_version: str = CODE_PARSER_SPEC_VERSION,
) -> CodeProjectionStore:
    return SQLiteCodeProjectionStore.open_writable(
        database_path, policy_revision=policy_revision, parser_spec_version=parser_spec_version
    )
