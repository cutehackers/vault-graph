"""Compatibility import for :mod:`vault_graph.operation.diagnostics.index_status_reader`."""

import sys

from vault_graph.operation.diagnostics import index_status_reader as _implementation
from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader as IndexStatusReader
from vault_graph.operation.diagnostics.index_status_reader import StatusReport as StatusReport

sys.modules[__name__] = _implementation
