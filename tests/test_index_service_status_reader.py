from pathlib import Path

import pytest

from vault_graph.indexing.index_service import IndexService
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class RecordingStatusReader:
    def __init__(self) -> None:
        self.scopes: list[QueryScope | None] = []
        self.report = object()

    def read(self, *, scope: QueryScope | None = None) -> object:
        self.scopes.append(scope)
        return self.report


def _service(tmp_path: Path, *, status_reader: RecordingStatusReader | None) -> IndexService:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    return IndexService(catalog=catalog, metadata_store=metadata_store, status_reader=status_reader)


def test_status_delegates_to_injected_status_reader(tmp_path: Path) -> None:
    reader = RecordingStatusReader()
    service = _service(tmp_path, status_reader=reader)
    scope = QueryScope(("default",), ("wiki",))

    assert service.status(scope=scope) is reader.report
    assert service.status() is reader.report
    assert reader.scopes == [scope, None]


def test_status_without_status_reader_fails_clearly(tmp_path: Path) -> None:
    service = _service(tmp_path, status_reader=None)

    with pytest.raises(RuntimeError, match="status reader is not configured"):
        service.status()
