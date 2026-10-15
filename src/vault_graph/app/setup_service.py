"""Compatibility import for :mod:`vault_graph.runtime_operations.setup_service`."""

import sys

from vault_graph.runtime_operations import setup_service as _implementation
from vault_graph.runtime_operations.setup_service import SetupReport as SetupReport
from vault_graph.runtime_operations.setup_service import SetupRequest as SetupRequest
from vault_graph.runtime_operations.setup_service import SetupService as SetupService

sys.modules[__name__] = _implementation
