"""Legacy default construction for explicitly requested runtime operations."""

from vault_graph.runtime_operations.indexing import OperationsIndexFactory


def default_index_factory() -> OperationsIndexFactory:
    from vault_graph.app.local_index_service_factory import LocalIndexServiceFactory

    return LocalIndexServiceFactory()
