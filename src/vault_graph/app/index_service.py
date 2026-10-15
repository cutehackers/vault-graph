"""Compatibility import for :mod:`vault_graph.indexing.index_service`."""

import sys

from vault_graph.indexing import index_service as _implementation
from vault_graph.indexing.index_service import IndexRunReport as IndexRunReport
from vault_graph.indexing.index_service import IndexService as IndexService
from vault_graph.indexing.index_service import StatusReport as StatusReport

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
