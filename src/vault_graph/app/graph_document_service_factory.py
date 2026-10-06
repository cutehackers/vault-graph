"""Connect MetadataStore to a separate, rebuildable document graph cache."""

from pathlib import Path

from graph_document import GraphLimits, ReadLimits

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_home import GraphHomeResolver
from vault_graph.extraction.vault_graph_document_adapter import VaultGraphDocumentAdapter
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class GraphDocumentServiceFactory:
    """Opening an adapter reads configuration only; synchronization is explicit."""

    def __init__(self, *, graph_home_path: Path) -> None:
        self._graph_home_path = graph_home_path

    def open_adapter(self, *, graph_limits: GraphLimits, read_limits: ReadLimits) -> VaultGraphDocumentAdapter:
        home = GraphHomeResolver().require_initialized(self._graph_home_path)
        catalog_service = CatalogService(graph_home_path=home.root_path)
        catalog = catalog_service.load_catalog()
        db_path = home.child_path("cache", "graph-document", "derived.sqlite3")
        manifest_dir = home.child_path("cache", "graph-document", "manifests")
        for target in (db_path, manifest_dir):
            catalog_service.assert_graph_home_write_target_safe(target_path=target, catalog=catalog)
        return VaultGraphDocumentAdapter(
            metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
            db_path=db_path,
            manifest_dir=manifest_dir,
            graph_limits=graph_limits,
            read_limits=read_limits,
        )
