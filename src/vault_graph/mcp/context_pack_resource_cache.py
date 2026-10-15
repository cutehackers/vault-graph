"""Compatibility import for :mod:`vault_graph.interface.mcp.context_pack_resource_cache`."""

import sys
from collections import OrderedDict as OrderedDict
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime

from vault_graph.context.pack.context_pack import ContextPack as ContextPack
from vault_graph.errors import ContextPackError as ContextPackError
from vault_graph.interface.mcp import context_pack_resource_cache as _implementation
from vault_graph.interface.mcp.context_pack_resource_cache import CachedContextPack as CachedContextPack
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache as ContextPackResourceCache
from vault_graph.interface.mcp.context_pack_resource_cache import _requested_scope_key as _requested_scope_key
from vault_graph.interface.mcp.context_pack_resource_cache import _utc_isoformat as _utc_isoformat

sys.modules[__name__] = _implementation
