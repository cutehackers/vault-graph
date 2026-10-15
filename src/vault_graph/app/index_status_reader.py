"""Compatibility import for :mod:`vault_graph.projection_diagnostics.index_status_reader`."""

import sys

from vault_graph.projection_diagnostics import index_status_reader as _implementation
from vault_graph.projection_diagnostics.index_status_reader import IndexStatusReader as IndexStatusReader
from vault_graph.projection_diagnostics.index_status_reader import StatusReport as StatusReport

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
