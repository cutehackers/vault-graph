"""Compatibility import for :mod:`vault_graph.operation.runtime.watch_service`."""

import sys

from vault_graph.operation.runtime import watch_service as _implementation
from vault_graph.operation.runtime.watch_service import WatchIterationReport as WatchIterationReport
from vault_graph.operation.runtime.watch_service import WatchReport as WatchReport
from vault_graph.operation.runtime.watch_service import WatchService as WatchService

sys.modules[__name__] = _implementation
