"""Compatibility import for :mod:`vault_graph.interface.http.http_service_factory`."""

import sys
from pathlib import Path as Path
from typing import TYPE_CHECKING as TYPE_CHECKING

from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory as ReadOnlyServiceFactory
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServices as ReadOnlyServices
from vault_graph.interface.http import http_service_factory as _implementation
from vault_graph.interface.http.http_service_factory import HttpServiceFactory as HttpServiceFactory

sys.modules[__name__] = _implementation
