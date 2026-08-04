from __future__ import annotations

from pathlib import Path

from vault_graph.app.graph_home import GraphHomeResolver
from vault_graph.app.path_guard import (
    assert_graph_home_outside_vaults,
    assert_graph_home_write_target_allowed,
    assert_target_outside_vaults,
)
from vault_graph.app.projection_generation import ProjectionGenerationManager
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry


class CatalogService:
    def __init__(self, *, graph_home_path: Path, embedding_cache_path: Path | None = None) -> None:
        self.graph_home_path = graph_home_path.expanduser().resolve()
        GraphHomeResolver().resolve(self.graph_home_path)
        self.config_path = self.graph_home_path / "configs" / "vaults.yaml"
        self.code_config_path = self.graph_home_path / "configs" / "repositories.yaml"
        active = ProjectionGenerationManager(self.graph_home_path).active_layout()
        projection_path = active.root_path if active is not None else self.graph_home_path
        self.metadata_path = projection_path / "metadata" / "metadata.sqlite3"
        self.vector_path = projection_path / "vector" / "chroma"
        # Status is run diagnostics, not part of the atomically published data bundle.
        self.vector_status_path = self.graph_home_path / "vector" / "status.json"
        self.graph_path = projection_path / "graph" / "graph.sqlite3"
        self.graph_status_path = self.graph_home_path / "graph" / "status.json"
        self.embedding_cache_path = (
            embedding_cache_path.expanduser().resolve()
            if embedding_cache_path is not None
            else Path("~/.cache/vault-graph/embeddings").expanduser().resolve()
        )

    def create_default_catalog(self, *, vault_root: Path, vault_id: str = "default") -> VaultCatalog:
        GraphHomeResolver().initialize(self.graph_home_path, vault_roots=(vault_root,))
        catalog = VaultCatalog.from_entries(
            entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=vault_root)],
            active_vault_id=vault_id,
        )
        self.assert_graph_home_safe(catalog)
        self.assert_graph_home_write_target_safe(target_path=self.config_path, catalog=catalog)
        catalog.save(self.config_path)
        return catalog

    def load_catalog(self) -> VaultCatalog:
        catalog = VaultCatalog.load(self.config_path)
        self.assert_graph_home_safe(catalog)
        return catalog

    def save_catalog(self, catalog: VaultCatalog) -> None:
        GraphHomeResolver().initialize(
            self.graph_home_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )
        self.assert_graph_home_safe(catalog)
        self.assert_graph_home_write_target_safe(target_path=self.config_path, catalog=catalog)
        catalog.save(self.config_path)

    def assert_graph_home_safe(self, catalog: VaultCatalog) -> None:
        assert_graph_home_outside_vaults(
            graph_home=self.graph_home_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )

    def assert_graph_home_write_target_safe(self, *, target_path: Path, catalog: VaultCatalog) -> None:
        assert_graph_home_write_target_allowed(
            graph_home=self.graph_home_path,
            target_path=target_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )

    def assert_cache_target_safe(self, *, target_path: Path, catalog: VaultCatalog) -> None:
        assert_target_outside_vaults(
            target_path=target_path,
            vault_roots=(entry.root_path for entry in catalog.entries()),
        )
