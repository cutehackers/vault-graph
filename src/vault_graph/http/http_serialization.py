"""Compatibility import for :mod:`vault_graph.interface.http.http_serialization`."""

import dataclasses as dataclasses
import math as math
import sys
from pathlib import Path as Path

from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.http import http_serialization as _implementation
from vault_graph.interface.http.http_serialization import _public_attrs as _public_attrs
from vault_graph.interface.http.http_serialization import domain_to_json_dict as domain_to_json_dict
from vault_graph.interface.http.http_serialization import domain_to_json_value as domain_to_json_value
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
