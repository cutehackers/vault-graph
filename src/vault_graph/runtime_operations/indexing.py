"""Compatibility import for :mod:`vault_graph.operation.runtime.indexing`."""

import sys
from pathlib import Path as Path
from typing import Protocol as Protocol

from vault_graph.indexing.index_service import IndexRunReport as IndexRunReport
from vault_graph.operation.runtime import indexing as _implementation
from vault_graph.operation.runtime.indexing import OperationsIndexBundle as OperationsIndexBundle
from vault_graph.operation.runtime.indexing import OperationsIndexer as OperationsIndexer
from vault_graph.operation.runtime.indexing import OperationsIndexFactory as OperationsIndexFactory
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
