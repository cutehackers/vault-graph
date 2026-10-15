"""Compatibility import for :mod:`vault_graph.interface.composition.adapters.runtime_indexing`."""

import sys

from vault_graph.interface.composition.adapters import runtime_indexing as _implementation
from vault_graph.interface.composition.adapters.runtime_indexing import default_index_factory as default_index_factory
from vault_graph.operation.runtime.indexing import OperationsIndexFactory as OperationsIndexFactory

sys.modules[__name__] = _implementation
