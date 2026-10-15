"""Indexing and resource lifetime required by setup and watch operations."""

from pathlib import Path
from typing import Protocol

from vault_graph.indexing.index_service import IndexRunReport
from vault_graph.ingestion.vault_catalog import QueryScope


class OperationsIndexer(Protocol):
    def run_apply(self, *, scope: QueryScope, full: bool = False) -> IndexRunReport: ...


class OperationsIndexBundle(Protocol):
    @property
    def index_service(self) -> OperationsIndexer: ...

    def close(self) -> None: ...


class OperationsIndexFactory(Protocol):
    def open(
        self,
        *,
        graph_home_path: Path,
        initialize_store: bool,
        transactional: bool = False,
        full: bool = False,
    ) -> OperationsIndexBundle: ...
