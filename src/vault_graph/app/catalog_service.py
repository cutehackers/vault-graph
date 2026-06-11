from __future__ import annotations

from pathlib import Path

from vault_graph.app.path_guard import (
    assert_state_outside_vaults,
    assert_target_outside_vaults,
    assert_write_target_allowed,
)
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry


class CatalogService:
    def __init__(self, *, state_path: Path, embedding_cache_path: Path | None = None) -> None:
        self.state_path = state_path.expanduser().resolve()
        self.config_path = self.state_path / "configs" / "vaults.yaml"
        self.metadata_path = self.state_path / "metadata" / "metadata.sqlite3"
        self.vector_path = self.state_path / "vector" / "chroma"
        self.vector_status_path = self.state_path / "vector" / "status.json"
        self.graph_path = self.state_path / "graph" / "graph.sqlite3"
        self.graph_status_path = self.state_path / "graph" / "status.json"
        self.embedding_cache_path = (
            embedding_cache_path.expanduser().resolve()
            if embedding_cache_path is not None
            else Path("~/.cache/vault-graph/embeddings").expanduser().resolve()
        )

    def create_default_catalog(self, *, vault_root: Path, vault_id: str = "default") -> VaultCatalog:
        catalog = VaultCatalog.from_entries(
            entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=vault_root)],
            active_vault_id=vault_id,
        )
        self.assert_state_safe(catalog)
        self.assert_write_target_safe(target_path=self.config_path, catalog=catalog)
        catalog.save(self.config_path)
        return catalog

    def load_catalog(self) -> VaultCatalog:
        catalog = VaultCatalog.load(self.config_path)
        self.assert_state_safe(catalog)
        return catalog

    def save_catalog(self, catalog: VaultCatalog) -> None:
        self.assert_state_safe(catalog)
        self.assert_write_target_safe(target_path=self.config_path, catalog=catalog)
        catalog.save(self.config_path)

    def assert_state_safe(self, catalog: VaultCatalog) -> None:
        assert_state_outside_vaults(
            state_path=self.state_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )

    def assert_write_target_safe(self, *, target_path: Path, catalog: VaultCatalog) -> None:
        assert_write_target_allowed(
            state_path=self.state_path,
            target_path=target_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )

    def assert_cache_target_safe(self, *, target_path: Path, catalog: VaultCatalog) -> None:
        assert_target_outside_vaults(
            target_path=target_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )
