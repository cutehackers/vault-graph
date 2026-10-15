"""Compatibility import for :mod:`vault_graph.operation.runtime.watch_service`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.indexing.index_service import IndexRunReport as IndexRunReport
from vault_graph.operation.runtime import watch_service as _implementation
from vault_graph.operation.runtime.indexing import OperationsIndexFactory as OperationsIndexFactory
from vault_graph.operation.runtime.watch_service import WatchIterationReport as WatchIterationReport
from vault_graph.operation.runtime.watch_service import WatchReport as WatchReport
from vault_graph.operation.runtime.watch_service import WatchService as WatchService
from vault_graph.operation.runtime.watch_service import _iteration_report as _iteration_report
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
